import logging
from typing import List, Dict, Any

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.critic")

STOP_WORDS = {"find", "give", "show", "get", "list", "with", "that", "their",
              "from", "into", "this", "have", "will", "they", "what", "which"}


class CriticAgent:
    """
    Validates enriched results and decides: PASS | RETRY | FAIL

    Structured feedback format:
    {
      "error": "<error_code>",
      "suggestion": "<what planner should change>",
      "confidence": 0.0–1.0,
      "adjust": { "industry": ..., "region": ..., "keywords": ..., "search_looseness": ... }
    }
    """

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("critic started")

        try:
            enriched = state.enriched_results

            if not enriched:
                return self._retry(state, {
                    "error": "empty_results",
                    "suggestion": "broaden search — no records returned from retrieval",
                    "confidence": 0.3,
                    "adjust": {"region": "global", "search_looseness": "broad"},
                })

            if len(enriched) < 2 and state.retry_count == 0:
                return self._retry(state, {
                    "error": "insufficient_results",
                    "suggestion": f"only {len(enriched)} result — expand region to global and loosen industry filter",
                    "confidence": 0.4,
                    "adjust": {"region": "global", "search_looseness": "broad"},
                })

            hallucination = self._detect_hallucination(state.query, state.plan or {})
            if hallucination:
                return self._retry(state, {
                    "error": "hallucinated_filter",
                    "suggestion": f"filter '{hallucination}' not grounded in query — reset to query-derived values only",
                    "confidence": 0.35,
                    "adjust": {"search_looseness": "strict"},
                })

            mismatch = self._detect_industry_mismatch(state.query, enriched, state.plan or {})
            if mismatch:
                industry = state.plan.get("filters", {}).get("industry", "AI")
                return self._retry(state, {
                    "error": "industry_mismatch",
                    "suggestion": f"{mismatch} — try broader industry alias or global region",
                    "confidence": 0.4,
                    "adjust": {"industry": "AI", "region": "global", "search_looseness": "broad"},
                })

            region_mismatch = self._detect_region_mismatch(state.query, enriched, state.plan or {})
            if region_mismatch:
                return self._retry(state, {
                    "error": "region_mismatch",
                    "suggestion": f"{region_mismatch} — expand region filter to include neighbouring markets",
                    "confidence": 0.4,
                    "adjust": {"region": "global", "search_looseness": "broad"},
                })

            if not self._is_relevant(state.query, enriched):
                keywords = self._extract_focus_keywords(state.query)
                return self._retry(state, {
                    "error": "low_relevance",
                    "suggestion": f"results not relevant — narrow keyword focus to: {keywords}",
                    "confidence": 0.35,
                    "adjust": {"keywords": keywords, "search_looseness": "strict"},
                })

            if self._has_low_quality(enriched):
                return self._retry(state, {
                    "error": "low_quality_data",
                    "suggestion": "too many records with missing required fields — try stricter data source filter",
                    "confidence": 0.4,
                    "adjust": {"search_looseness": "strict"},
                })

            if not state.signals:
                return self._retry(state, {
                    "error": "no_signals",
                    "suggestion": "no buying signals detected — shift industry to signal-rich verticals (AI/fintech)",
                    "confidence": 0.3,
                    "adjust": {"industry": "AI", "search_looseness": "broad"},
                })

            # PASS
            state.set_critic("PASS", "relevance OK, quality OK, signals present, no hallucinations")
            state.add_trace("critic passed: relevance OK, quality OK, signals present, no hallucinations")
            return state

        except Exception as e:
            logger.error(f"critic error: {str(e)}")
            state.errors.append(str(e))
            return self._fail(state, f"critic exception: {str(e)}")

    # ── Hallucination detection ───────────────────────────────────────

    def _detect_hallucination(self, query: str, plan: Dict[str, Any]) -> str:
        query_lower = query.lower()
        filters = plan.get("filters", {})
        industry = filters.get("industry", "").lower()
        region = filters.get("region", "global").lower()

        industry_keywords = {
            "fintech":    ["fintech", "finance", "banking", "payments", "financial"],
            "health":     ["health", "medical", "biotech", "healthcare", "healthtech"],
            "healthtech": ["health", "medical", "biotech", "healthcare", "healthtech"],
            "saas":       ["saas", "software", "cloud", "platform"],
            "ai":         ["ai", "ml", "machine learning", "artificial intelligence",
                           "saas", "software", "tech", "startup", "company", "companies",
                           "growth", "high-growth"],
        }

        if industry and industry not in ("ai", "saas"):
            valid_kws = industry_keywords.get(industry, [])
            if not any(kw in query_lower for kw in valid_kws):
                return f"industry '{industry}' not grounded in query"

        if region == "eu" and not any(
            w in query_lower for w in ["eu", "europe", "european"]
        ):
            return f"region 'EU' not grounded in query"

        return ""

    # ── Industry mismatch ─────────────────────────────────────────────

    def _detect_industry_mismatch(self, query: str, data: List[Dict], plan: Dict) -> str:
        expected = plan.get("filters", {}).get("industry", "").lower()
        if not expected or expected in ("ai", "saas", "global"):
            return ""
        matched = sum(
            1 for r in data
            if expected in r.get("industry", "").lower()
            or r.get("industry", "").lower() in expected
        )
        if matched == 0:
            return f"0/{len(data)} results match expected industry '{expected}'"
        if matched < len(data) / 2:
            return f"only {matched}/{len(data)} results match industry '{expected}'"
        return ""

    # ── Region mismatch ───────────────────────────────────────────────

    def _detect_region_mismatch(self, query: str, data: List[Dict], plan: Dict) -> str:
        expected = plan.get("filters", {}).get("region", "global").lower()
        if expected == "global":
            return ""
        region_aliases = {"eu": ["eu", "europe"], "us": ["us", "usa"], "uk": ["uk"]}
        valid = region_aliases.get(expected, [expected])
        matched = sum(1 for r in data if r.get("region", "").lower() in valid)
        if matched == 0:
            return f"0/{len(data)} results match expected region '{expected}'"
        return ""

    # ── Relevance check ───────────────────────────────────────────────

    def _is_relevant(self, query: str, data: List[Dict]) -> bool:
        keywords = [
            w for w in query.lower().split()
            if len(w) > 3 and w not in STOP_WORDS
        ]
        for record in data:
            text = str(record).lower()
            if sum(1 for kw in keywords if kw in text) >= 2:
                return True
        return False

    def _extract_focus_keywords(self, query: str) -> List[str]:
        return [
            w for w in query.lower().split()
            if len(w) > 4 and w not in STOP_WORDS
        ][:4]

    # ── Quality check ─────────────────────────────────────────────────

    def _has_low_quality(self, data: List[Dict]) -> bool:
        required = ["company", "industry", "region", "employees", "funding"]
        bad = sum(
            1 for record in data
            if any(not record.get(f) for f in required)
            or record.get("confidence") is None
        )
        # Fail only if majority of records are bad
        return bad > len(data) / 2

    # ── Verdict helpers ───────────────────────────────────────────────

    def _retry(self, state: AgentState, feedback: Dict[str, Any]) -> AgentState:
        reason = feedback.get("suggestion", "unknown reason")
        logger.warning(f"critic RETRY: {feedback.get('error')} — {reason}")
        state.set_critic("RETRY", reason)
        # Store full structured feedback so planner can use it
        state.memory["critic_structured_feedback"] = feedback
        state.add_trace(
            f"critic retry [{feedback.get('error')}]: {reason} "
            f"(confidence: {feedback.get('confidence', 0):.0%})"
        )
        return state

    def _fail(self, state: AgentState, reason: str) -> AgentState:
        logger.error(f"critic FAIL: {reason}")
        state.set_critic("FAIL", reason)
        state.errors.append(reason)
        return state