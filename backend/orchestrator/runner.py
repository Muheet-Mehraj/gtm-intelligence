import logging
from typing import Dict, Any

from backend.orchestrator.state import AgentState

from backend.agents.planner import PlannerAgent
from backend.agents.retrieval import RetrievalAgent
from backend.agents.enrichment import EnrichmentAgent
from backend.agents.critic import CriticAgent
from backend.agents.gtm_strategy import GTMStrategyAgent

from backend.memory.short_term import SessionMemory
from backend.observability.tracer import Tracer

logger = logging.getLogger("gtm.runner")


class Runner:
    def __init__(self):
        self.planner = PlannerAgent()
        self.retrieval = RetrievalAgent()
        self.enrichment = EnrichmentAgent()
        self.critic = CriticAgent()
        self.gtm = GTMStrategyAgent()

        self.memory = SessionMemory()
        self.tracer = Tracer()

    
    # MAIN PIPELINE (REST)


    def run(self, query: str) -> Dict[str, Any]:
        #  CACHE 
        cached = self.memory.get(query)
        if cached:
            logger.info("cache hit")
            return cached

        state = AgentState(query=query)
        logger.info("pipeline started")

        while state.should_retry():
            logger.info(f"attempt {state.retry_count + 1}")
            self.tracer.start(f"attempt_{state.retry_count + 1}")

            try:
                #  PLANNER 
                self.tracer.start("planner")
                state = self.planner(state)

                #  RETRIEVAL 
                self.tracer.start("retrieval")
                state = self.retrieval(state)

                #  ENRICHMENT 
                self.tracer.start("enrichment")
                state = self.enrichment(state)

                #  CRITIC 
                self.tracer.start("critic")
                state = self._safe_critic(state)

                #  DECISION 
                if state.critic_status == "PASS":
                    logger.info("critic passed")
                    return self._finalize_success(state, query)

                if state.critic_status == "RETRY":
                    logger.warning(f"retry triggered: {state.critic_feedback}")
                    state.memory["critic_feedback"] = state.critic_feedback or ""
                    state.increment_retry()
                    state.reset_for_retry()
                    continue

                if state.critic_status == "FAIL":
                    logger.error("critic hard fail")
                    state.errors.append("validation failed")
                    break

            except Exception as e:
                logger.error(f"pipeline error: {str(e)}")
                state.errors.append(str(e))
                state.increment_retry()

        #  FALLBACK PATH 
        return self._finalize_fallback(state, query)

    # 
    # SAFE CRITIC (isolated)
    # 

    def _safe_critic(self, state: AgentState) -> AgentState:
        try:
            state = self.critic(state)
            logger.info(f"critic status: {state.critic_status}")
            return state
        except Exception as e:
            logger.error(f"critic crashed: {e}")

            state.set_critic("PASS", f"critic unavailable: {str(e)}")
            state.reasoning_trace.append("critic failed — defaulting to PASS")

            return state

    # ─────────────────────────────────────────────
    # SUCCESS PATH
    # ─────────────────────────────────────────────

    def _finalize_success(self, state: AgentState, query: str) -> Dict[str, Any]:
        try:
            self.tracer.start("gtm_strategy")
            state = self.gtm(state)
            state.reasoning_trace.append("GTM strategy generated")
        except Exception as e:
            logger.error(f"GTM error: {e}")
            state.gtm_strategy = self._empty_gtm()
            state.reasoning_trace.append(f"GTM error: {str(e)}")

        state.confidence = self._compute_confidence(state)

        result = self._build_response(state)
        self.memory.set(query, result)

        return result

    # ─────────────────────────────────────────────
    # FALLBACK PATH (after retries exhausted)
    # ─────────────────────────────────────────────

    def _finalize_fallback(self, state: AgentState, query: str) -> Dict[str, Any]:
        logger.warning("max retries reached — fallback mode")

        state.reasoning_trace.append("max retries reached — fallback execution")

        if state.enriched_results:
            try:
                state = self.gtm(state)
                state.reasoning_trace.append("GTM generated on fallback data")
            except Exception as e:
                logger.error(f"GTM fallback failed: {e}")
                state.gtm_strategy = self._empty_gtm()

        state.confidence = max(0.3, self._compute_confidence(state))

        result = self._build_response(state)
        self.memory.set(query, result)

        return result

    # ─────────────────────────────────────────────
    # STEP EXECUTION (WebSocket compatibility)
    # ─────────────────────────────────────────────

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

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _build_response(self, state: AgentState) -> Dict[str, Any]:
        return {
            "plan": state.plan,
            "results": state.enriched_results,
            "signals": state.signals,
            "gtm_strategy": state.gtm_strategy or self._empty_gtm(),
            "confidence": state.confidence,
            "reasoning_trace": state.reasoning_trace,
            "errors": state.errors,
            "retry_count": state.retry_count,
            "spans": self.tracer.get_trace(),
        }

    def _compute_confidence(self, state: AgentState) -> float:
        if not state.enriched_results:
            return 0.3

        if state.retry_count == 0:
            return 0.9

        return max(0.5, 1 - (state.retry_count * 0.2))

    def _empty_gtm(self):
        return {
            "hooks": [],
            "angles": [],
            "email_snippets": []
        }