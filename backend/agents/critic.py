import logging
from typing import List, Dict, Any

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.critic")


class CriticAgent:
    """
    Validates enriched results and decides: PASS | RETRY | FAIL

    Checks:
    - Result relevance to original query
    - Data quality (missing required fields)
    - Signal presence
    - Filter hallucination (are plan filters grounded in the query?)
    """

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("critic started")

        try:
            enriched = state.enriched_results

            if not enriched:
                return self._retry(state, "no enriched results")
            if len(enriched) < 3 and state.retry_count == 0:
                return self._retry(state, "insufficient results — expanding search")

            # Hallucination check: are the plan's filters grounded in the query?
            hallucination = self._detect_hallucination(state.query, state.plan or {})
            if hallucination:
                return self._retry(state, f"hallucinated filter: {hallucination}")

            if not self._is_relevant(state.query, enriched):
                return self._retry(state, "results not relevant to query")

            if self._has_low_quality(enriched):
                return self._retry(state, "low quality data — missing required fields")

            if not state.signals:
                return self._retry(state, "no signals detected")

            state.set_critic("PASS", "valid results — all checks passed")
            state.add_trace("critic passed: relevance OK, quality OK, signals present, no hallucinations")

            return state

        except Exception as e:
            logger.error(f"critic error: {str(e)}")
            state.errors.append(str(e))
            return self._fail(state, "critic failure")

    # ── Hallucination detection ───────────────────────────────────────

    def _detect_hallucination(self, query: str, plan: Dict[str, Any]) -> str:
        """
        Check that plan filters are grounded in the query.
        Returns a description of the hallucination if found, else empty string.
        """
        query_lower = query.lower()
        filters = plan.get("filters", {})

        industry = filters.get("industry", "").lower()
        region = filters.get("region", "").lower()

        # Industry hallucination: if no industry keyword in query, industry must default to AI
        industry_keywords = {
            "fintech": ["fintech", "finance", "banking", "payments"],
            "health": ["health", "medical", "biotech", "healthcare"],
            "ai": ["ai", "ml", "machine learning", "artificial intelligence", "saas", "software"],
        }

        if industry and industry != "ai":
            valid_keywords = industry_keywords.get(industry, [])
            if not any(kw in query_lower for kw in valid_keywords):
                return f"industry '{industry}' not grounded in query"

        # Region hallucination: if US/EU selected but no regional keyword in query
        if region == "us" and not any(w in query_lower for w in ["us", "united states", "america", "american"]):
            # Not a hard fail — US is a reasonable default for tech queries
            pass

        if region == "eu" and not any(w in query_lower for w in ["eu", "europe", "european"]):
            return f"region 'EU' not grounded in query"

        return ""

    # ── Relevance check ───────────────────────────────────────────────

    def _is_relevant(self, query: str, data: List[Dict[str, Any]]) -> bool:
        keywords = [w for w in query.lower().split() if len(w) > 3]
        plan_industry_terms = ["ai", "fintech", "health", "saas", "software", "tech"]

        for record in data:
            text = str(record).lower()
            # Match on query keywords OR on common industry terms (result may not echo query verbatim)
            if any(word in text for word in keywords):
                return True
            if any(term in text for term in plan_industry_terms):
                return True

        return False

    # ── Quality check ─────────────────────────────────────────────────

    def _has_low_quality(self, data: List[Dict[str, Any]]) -> bool:
        for record in data:
            if not record.get("company"):
                return True
            if record.get("confidence") is None:
                return True
        return False

    # ── Verdict helpers ───────────────────────────────────────────────

    def _retry(self, state: AgentState, reason: str) -> AgentState:
        logger.warning(f"critic retry: {reason}")
        state.set_critic("RETRY", reason)
        state.add_trace(f"critic retry: {reason}")
        return state

    def _fail(self, state: AgentState, reason: str) -> AgentState:
        logger.error(f"critic fail: {reason}")
        state.set_critic("FAIL", reason)
        state.errors.append(reason)
        return state