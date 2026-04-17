import json
from fastapi import WebSocket, WebSocketDisconnect
from backend.orchestrator.runner import Runner

runner = Runner()


async def stream_run(websocket: WebSocket):
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        query = data.get("query", "")

        if not query:
            await websocket.send_json({"type": "error", "message": "No query provided"})
            return

        state = runner.create_state(query)

        # Helper to emit agent status updates
        async def emit(step: str, status: str, detail: str = "", payload: dict = {}):
            await websocket.send_json({
                "type": "agent_update",
                "step": step,
                "status": status,   # "running" | "done" | "error" | "retry"
                "detail": detail,
                "data": payload,
            })

        # ── Planner ──────────────────────────────────────────────────
        await emit("planner", "running", "Decomposing query into execution plan...")
        try:
            state = runner.run_planner(state)
            await emit("planner", "done", "Execution plan created", {
                "entity_type": state.plan.get("entity_type", ""),
                "tasks": state.plan.get("tasks", []),
                "confidence": state.plan.get("confidence", 0),
                "strategy": state.plan.get("strategy", ""),
            })
        except Exception as e:
            await emit("planner", "error", str(e))
            await websocket.send_json({"type": "fatal", "message": "Planner failed"})
            return

        # ── Retry loop ───────────────────────────────────────────────
        MAX_RETRIES = 2
        attempt = 0

        while attempt <= MAX_RETRIES:

            # ── Retrieval ────────────────────────────────────────────
            await emit("retrieval", "running", f"Querying data sources (attempt {attempt + 1})...")
            try:
                state = runner.run_retrieval(state)
                await emit("retrieval", "done", f"Retrieved {len(state.raw_results)} records", {
                    "count": len(state.raw_results)
                })
            except Exception as e:
                await emit("retrieval", "error", str(e))
                break

            # ── Enrichment ───────────────────────────────────────────
            await emit("enrichment", "running", "Enriching records with signals and ICP scores...")
            try:
                state = runner.run_enrichment(state)
                await emit("enrichment", "done", f"Enriched {len(state.enriched_results)} records", {
                    "count": len(state.enriched_results)
                })
            except Exception as e:
                await emit("enrichment", "error", str(e))
                break

            # ── Critic ───────────────────────────────────────────────
            await emit("critic", "running", "Validating results for relevance and hallucinations...")
            try:
                state = runner.run_critic(state)
                verdict = state.critic_status
                reason = state.critic_feedback or ""

                if verdict == "PASS":
                    await emit("critic", "done",
                        f"Results approved — {reason}",
                        {"status": "PASS", "feedback": reason}
                    )
                    break  # exit retry loop — move to GTM

                elif verdict == "FAIL":
                    await emit("critic", "error",
                        f"Hard validation failure: {reason}",
                        {"status": "FAIL", "feedback": reason}
                    )
                    break

                else:  # RETRY
                    if attempt >= MAX_RETRIES:
                        await emit("critic", "retry",
                            f"Max retries reached. Accepting with reduced confidence. Reason: {reason}",
                            {"status": "RETRY", "feedback": reason, "retry_count": attempt}
                        )
                        break
                    else:
                        await emit("critic", "retry",
                            f"Rejected (attempt {attempt + 1}): {reason} — re-planning...",
                            {"reason": reason, "retry_count": attempt + 1}
                        )
                        # Feed critic reason back to planner's memory before next loop
                        state.memory["critic_feedback"] = reason
                        state.reset_for_retry()
                        state.increment_retry()
                        state = runner.run_planner(state)
                        await emit("planner", "done",
                            f"Re-planned with critic feedback (attempt {attempt + 2})",
                            {
                                "entity_type": state.plan.get("entity_type", ""),
                                "strategy": state.plan.get("strategy", ""),
                            }
                        )
                        attempt += 1
                        continue

            except Exception as e:
                await emit("critic", "error", str(e))
                break

        # ── GTM Strategy ─────────────────────────────────────────────
        await emit("gtm_strategy", "running", "Generating personalized outreach hooks and email snippets...")
        try:
            state = runner.run_gtm(state)
            gtm = state.gtm_strategy or {}
            await emit("gtm_strategy", "done", "GTM strategy generated", {
                "hook_count": len(gtm.get("hooks", [])),
            })
        except Exception as e:
            await emit("gtm_strategy", "error", str(e))

        # ── Compute final confidence ──────────────────────────────────
        if not state.enriched_results:
            confidence = 0.3
        elif state.retry_count == 0:
            confidence = 0.9
        else:
            confidence = max(0.5, 1 - (state.retry_count * 0.2))

        state.confidence = confidence

        # ── Final result payload ──────────────────────────────────────
        await websocket.send_json({
            "type": "result",
            "data": {
                "plan": state.plan,
                "results": state.enriched_results,
                "signals": state.signals,
                "gtm_strategy": state.gtm_strategy or {"hooks": [], "angles": [], "email_snippets": []},
                "confidence": state.confidence,
                "reasoning_trace": state.reasoning_trace,
                "errors": state.errors,
                "retry_count": state.retry_count,
            }
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass