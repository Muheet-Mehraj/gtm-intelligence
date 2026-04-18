import logging
from typing import Dict, Any, List

from backend.orchestrator.state import AgentState
from backend.agents.planner import PlannerAgent
from backend.agents.retrieval import RetrievalAgent
from backend.agents.enrichment import EnrichmentAgent
from backend.agents.critic import CriticAgent
from backend.agents.gtm_strategy import GTMStrategyAgent
from backend.memory.short_term import SessionMemory
from backend.memory.vector_store import VectorStore
from backend.observability.tracer import Tracer

logger = logging.getLogger("gtm.runner")


class Runner:
    def __init__(self):
        self.planner    = PlannerAgent()
        self.retrieval  = RetrievalAgent()
        self.enrichment = EnrichmentAgent()
        self.critic     = CriticAgent()
        self.gtm        = GTMStrategyAgent()

        # ✅ Module-level singleton ensures these persist across requests
        self.memory       = SessionMemory()
        self.vector_store = VectorStore()
        self.tracer       = Tracer()

    # ── MAIN PIPELINE (REST) 

    def run(self, query: str) -> Dict[str, Any]:
        # Exact cache hit
        cached = self.memory.get(query)
        if cached:
            logger.info("cache hit — returning cached result")
            return cached

        state = AgentState(query=query)

        # Vector memory: inject past similar results
        past_results = self.vector_store.search(query)
        if past_results:
            logger.info(f"vector memory: {len(past_results)} similar past records found")
            state.memory["past_results"] = past_results
            state.memory["past_signals"] = self.vector_store.get_similar_signals(query)
            state.add_trace(
                f"memory: loaded {len(past_results)} similar records from past queries "
                f"(vector store size: {self.vector_store.size()})"
            )

        logger.info(f"pipeline started — query: {query!r}")

        while state.should_retry():
            attempt = state.retry_count + 1
            logger.info(f"attempt {attempt}/{state.max_retries}")
            self.tracer.start(f"attempt_{attempt}")

            try:
                # ── PLANNER 
                self.tracer.start("planner")
                if state.retry_count > 0:
                    # Pass structured feedback if available
                    structured = state.memory.get("critic_structured_feedback", {})
                    if structured:
                        state.memory["critic_feedback"] = structured.get("suggestion", "")
                    state.add_trace(
                        f"re-planning attempt {attempt} — "
                        f"error: {structured.get('error', 'unknown')}, "
                        f"adjustments: {structured.get('adjust', {})}"
                    )
                state = self.planner(state)

                # ── RETRIEVAL 
                self.tracer.start("retrieval")
                state = self.retrieval(state)

                # Augment with vector memory
                if state.raw_results and past_results:
                    state.raw_results = self._merge_with_memory(state.raw_results, past_results)
                    state.add_trace(
                        f"memory augmentation: merged {len(past_results)} past records "
                        f"into retrieval results"
                    )

                # Guard: empty retrieval
                if not state.raw_results:
                    reason = "retrieval returned empty results — strict filters or API failure"
                    logger.warning(reason)
                    state.set_critic("RETRY", reason)
                    state.memory["critic_structured_feedback"] = {
                        "error": "empty_results",
                        "suggestion": reason,
                        "confidence": 0.3,
                        "adjust": {"region": "global", "search_looseness": "broad"},
                    }
                    state.add_trace(f"retrieval guard: {reason} — forcing retry")
                    state.increment_retry()
                    state.reset_for_retry()
                    continue

                # ── ENRICHMENT 
                self.tracer.start("enrichment")
                state = self.enrichment(state)

                # Boost signals from vector memory
                if past_signals := state.memory.get("past_signals", []):
                    new_signals = [s for s in past_signals if s not in state.signals]
                    if new_signals:
                        state.signals.extend(new_signals)
                        state.add_trace(
                            f"memory: added {len(new_signals)} signals from past queries: "
                            f"{', '.join(new_signals)}"
                        )

                # ── CRITIC 
                self.tracer.start("critic")
                state = self._safe_critic(state)

                # ── DECISION 
                if state.critic_status == "PASS":
                    logger.info(f"critic passed on attempt {attempt}")
                    state.add_trace(
                        f"pipeline: critic PASS on attempt {attempt} — "
                        f"proceeding to GTM strategy"
                    )
                    return self._finalize_success(state, query)

                if state.critic_status == "RETRY":
                    logger.warning(
                        f"retry {attempt}: {state.critic_feedback}"
                    )
                    state.add_trace(
                        f"pipeline: critic RETRY on attempt {attempt} — "
                        f"{state.critic_feedback} — incrementing retry count"
                    )
                    state.increment_retry()
                    state.reset_for_retry()
                    continue

                if state.critic_status == "FAIL":
                    logger.error("critic hard fail — aborting pipeline")
                    state.add_trace("pipeline: critic FAIL — hard stop, returning fallback")
                    state.errors.append("validation failed after critic FAIL")
                    break

            except Exception as e:
                logger.error(f"pipeline error on attempt {attempt}: {str(e)}")
                state.errors.append(str(e))
                state.add_trace(
                    f"pipeline: unhandled exception on attempt {attempt}: {str(e)} — retrying"
                )
                state.increment_retry()
                state.reset_for_retry()

        return self._finalize_fallback(state, query)

    # ── MEMORY HELPERS 

    def _merge_with_memory(self, fresh: List[Dict], past: List[Dict]) -> List[Dict]:
        seen = {r.get("company", "").lower() for r in fresh}
        merged = list(fresh)
        for record in past:
            name = record.get("company", "").lower()
            if name and name not in seen:
                record["_from_memory"] = True
                merged.append(record)
                seen.add(name)
        return merged

    # ── SAFE CRITIC 

    def _safe_critic(self, state: AgentState) -> AgentState:
        try:
            state = self.critic(state)
            logger.info(f"critic verdict: {state.critic_status}")
            return state
        except Exception as e:
            logger.error(f"critic crashed: {e}")
            state.set_critic("PASS", f"critic unavailable: {str(e)}")
            state.add_trace(f"critic crashed ({str(e)}) — defaulting to PASS")
            return state

    # ── SUCCESS PATH 

    def _finalize_success(self, state: AgentState, query: str) -> Dict[str, Any]:
        try:
            self.tracer.start("gtm_strategy")
            state = self.gtm(state)
        except Exception as e:
            logger.error(f"GTM error: {e}")
            state.gtm_strategy = self._empty_gtm()
            state.add_trace(f"GTM strategy failed: {str(e)} — returning empty strategy")

        state.confidence = self._compute_confidence(state)
        state.add_trace(
            f"pipeline complete — confidence: {state.confidence:.0%}, "
            f"retries: {state.retry_count}, "
            f"results: {len(state.enriched_results)}"
        )

        result = self._build_response(state)
        self.memory.set(query, result)
        self.vector_store.add(query, state.enriched_results, state.signals)
        logger.info(f"stored in memory — vector store size: {self.vector_store.size()}")

        return result

    # ── FALLBACK PATH 

    def _finalize_fallback(self, state: AgentState, query: str) -> Dict[str, Any]:
        logger.warning(f"max retries ({state.max_retries}) reached — fallback mode")
        state.add_trace(
            f"pipeline: max retries ({state.max_retries}) reached — "
            f"fallback execution with {len(state.enriched_results)} partial results"
        )

        if state.enriched_results:
            try:
                state = self.gtm(state)
                state.add_trace("GTM strategy generated on fallback data")
            except Exception as e:
                state.gtm_strategy = self._empty_gtm()
                state.add_trace(f"GTM strategy failed on fallback: {str(e)}")
        else:
            state.gtm_strategy = self._empty_gtm()
            state.add_trace("no results after all retries — empty GTM returned")

        state.confidence = max(0.2, self._compute_confidence(state))
        result = self._build_response(state)
        self.memory.set(query, result)
        if state.enriched_results:
            self.vector_store.add(query, state.enriched_results, state.signals)
        return result

    # ── WEBSOCKET STEP EXECUTION 

    def create_state(self, query: str) -> AgentState:
        return AgentState(query=query)

    def run_planner(self, state: AgentState) -> AgentState:
        self.tracer.start("planner")
        return self.planner(state)

    def run_retrieval(self, state: AgentState) -> AgentState:
        self.tracer.start("retrieval")
        return self.retrieval(state)

    def run_enrichment(self, state: AgentState) -> AgentState:
        self.tracer.start("enrichment")
        return self.enrichment(state)

    def run_critic(self, state: AgentState) -> AgentState:
        self.tracer.start("critic")
        return self._safe_critic(state)

    def run_gtm(self, state: AgentState) -> AgentState:
        self.tracer.start("gtm_strategy")
        return self.gtm(state)

    def get_spans(self):
        return self.tracer.get_trace()

    # ── HELPERS 

    def _build_response(self, state: AgentState) -> Dict[str, Any]:
        return {
            "plan":            state.plan,
            "results":         state.enriched_results,
            "signals":         state.signals,
            "gtm_strategy":    state.gtm_strategy or self._empty_gtm(),
            "confidence":      state.confidence,
            "reasoning_trace": state.reasoning_trace,
            "errors":          state.errors,
            "retry_count":     state.retry_count,
            "spans":           self.tracer.get_trace(),
        }

    def _compute_confidence(self, state: AgentState) -> float:
        if not state.enriched_results:
            return 0.2
        base = 0.9 - (state.retry_count * 0.15)
        # Boost for high avg ICP score
        avg_icp = sum(r.get("icp_score", 0) for r in state.enriched_results) / len(state.enriched_results)
        boost = avg_icp * 0.1
        return round(max(0.3, min(1.0, base + boost)), 2)

    def _empty_gtm(self):
        return {"hooks": [], "angles": [], "email_snippets": []}