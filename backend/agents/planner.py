import logging
from typing import Dict, Any

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.planner")


class PlannerAgent:
    """
    Converts user query into a structured execution plan.
    Reads critic feedback from state.memory on retries to adjust strategy.
    """

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("planner started")

        try:
            critic_feedback = state.memory.get("critic_feedback", "")
            plan = self._create_plan(state.query, critic_feedback)
            state.plan = plan

            if critic_feedback:
                state.add_trace(
                    f"planner re-planned using critic feedback: {critic_feedback}"
                )
            else:
                state.add_trace("planner created execution plan")

            state.add_log(f"plan: {plan}")
            return state

        except Exception as e:
            logger.error(f"planner error: {str(e)}")
            state.errors.append(str(e))
            state.plan = self._fallback_plan(state.query)
            return state

    def _create_plan(self, query: str, critic_feedback: str = "") -> Dict[str, Any]:
        query_lower = query.lower()

        # Defaults 
        industry = "AI"
        region = "global"

        # Region extraction 
        if "us" in query_lower or "united states" in query_lower or "america" in query_lower:
            region = "US"
        elif "europe" in query_lower or "eu" in query_lower:
            region = "EU"

        # Industry extraction 
        if "fintech" in query_lower or "finance" in query_lower or "banking" in query_lower:
            industry = "fintech"
        elif "health" in query_lower or "medical" in query_lower or "biotech" in query_lower:
            industry = "health"

        #  Critic-driven adjustments 

        # 1. Not relevant → broaden region
        if critic_feedback and "not relevant" in critic_feedback.lower():
            region = "global"
            logger.info("planner broadened region to global based on critic feedback")

        # 2. Insufficient results → expand search
        if critic_feedback and "insufficient results" in critic_feedback.lower():
            if region != "global":
                region = "global"
            else:
                industry = "AI"  # fallback expansion if already global

            logger.info("planner expanded search scope due to insufficient results")

        # 3. No signals → reset industry
        if critic_feedback and "no signals" in critic_feedback.lower():
            industry = "AI"
            logger.info("planner reset industry to AI based on critic feedback")

        #  Confidence 
        confidence = 0.6 if critic_feedback else 0.75

        return {
            "entity_type": "companies",
            "filters": {
                "industry": industry,
                "region": region,
                "keywords": [query],
            },
            "tasks": ["search", "enrich", "analyze", "generate_outreach"],
            "strategy": (
                "feedback-adjusted planning"
                if critic_feedback
                else "deterministic planning"
            ),
            "confidence": confidence,
            "critic_feedback_applied": critic_feedback or None,
        }

    def _fallback_plan(self, query: str) -> Dict[str, Any]:
        return {
            "entity_type": "companies",
            "filters": {
                "industry": "AI",
                "region": "global",
                "keywords": [query],
            },
            "tasks": ["search", "enrich"],
            "strategy": "fallback planning",
            "confidence": 0.4,
        }