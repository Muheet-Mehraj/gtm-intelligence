import logging
from typing import Dict, Any, List

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.planner")

# Strategy modes
STRATEGY_BROAD       = "broad_search"
STRATEGY_NICHE       = "niche_focus"
STRATEGY_SIGNAL      = "signal_driven"
STRATEGY_FALLBACK    = "fallback_planning"
STRATEGY_FEEDBACK    = "feedback_adjusted_planning"


class PlannerAgent:
    """
    Converts user query into a structured execution plan.
    On retries, consumes structured critic feedback to deeply adapt:
      - strategy mode (broad / niche / signal-driven)
      - industry + region filters
      - keywords (refined, not just reset)
      - search_looseness (strict / broad)
      - confidence estimate
    """

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("planner started")

        try:
            structured_fb = state.memory.get("critic_structured_feedback", {})
            plain_fb      = state.memory.get("critic_feedback", "")

            plan = self._create_plan(state.query, structured_fb, plain_fb, state.retry_count)
            state.plan = plan

            if structured_fb or plain_fb:
                error_code = structured_fb.get("error", "unknown")
                state.add_trace(
                    f"planner re-planned [attempt {state.retry_count + 1}] "
                    f"using critic feedback [{error_code}]: {plan['strategy']} — "
                    f"industry={plan['filters']['industry']}, "
                    f"region={plan['filters']['region']}, "
                    f"looseness={plan.get('search_looseness', 'strict')}"
                )
            else:
                state.add_trace(
                    f"planner created execution plan — "
                    f"strategy={plan['strategy']}, "
                    f"industry={plan['filters']['industry']}, "
                    f"region={plan['filters']['region']}"
                )

            state.add_log(f"plan: {plan}")
            return state

        except Exception as e:
            logger.error(f"planner error: {str(e)}")
            state.errors.append(str(e))
            state.plan = self._fallback_plan(state.query)
            return state

    def _create_plan(
        self,
        query: str,
        structured_fb: Dict[str, Any],
        plain_fb: str,
        retry_count: int,
    ) -> Dict[str, Any]:
        query_lower = query.lower()

        # ── Base extraction 
        industry = self._extract_industry(query_lower)
        region   = self._extract_region(query_lower)
        keywords = self._extract_keywords(query_lower)
        strategy = STRATEGY_NICHE if industry != "AI" else STRATEGY_SIGNAL
        search_looseness = "strict"
        confidence = 0.75

        # ── Deep adaptation from structured critic feedback 
        if structured_fb:
            error_code = structured_fb.get("error", "")
            adjust     = structured_fb.get("adjust", {})
            fb_conf    = structured_fb.get("confidence", 0.5)

            # Apply all critic-suggested adjustments
            if "industry" in adjust:
                industry = adjust["industry"]
                logger.info(f"planner: industry adjusted to '{industry}' per critic")

            if "region" in adjust:
                region = adjust["region"]
                logger.info(f"planner: region adjusted to '{region}' per critic")

            if "search_looseness" in adjust:
                search_looseness = adjust["search_looseness"]

            if "keywords" in adjust:
                # Merge critic-suggested keywords with original (don't discard original intent)
                extra = adjust["keywords"]
                keywords = list(dict.fromkeys(extra + keywords))[:6]

            # Strategy mode based on error type
            if error_code in ("empty_results", "insufficient_results"):
                strategy = STRATEGY_BROAD
                search_looseness = "broad"
                confidence = max(0.4, fb_conf)

            elif error_code in ("low_relevance",):
                strategy = STRATEGY_SIGNAL
                # Narrow keywords to only high-signal terms
                keywords = [k for k in keywords if len(k) > 5][:4]
                confidence = max(0.45, fb_conf)

            elif error_code in ("industry_mismatch", "region_mismatch"):
                strategy = STRATEGY_BROAD
                confidence = max(0.4, fb_conf)

            elif error_code in ("hallucinated_filter",):
                # Reset to purely query-derived values
                industry = self._extract_industry(query_lower)
                region   = self._extract_region(query_lower)
                strategy = STRATEGY_NICHE
                confidence = max(0.5, fb_conf)

            elif error_code in ("no_signals",):
                industry = "AI"
                strategy = STRATEGY_SIGNAL
                search_looseness = "broad"
                confidence = max(0.35, fb_conf)

            # Confidence degrades with each retry
            confidence = round(max(0.2, confidence - (retry_count * 0.1)), 2)

        elif plain_fb:
            # Legacy plain text feedback (backward compat)
            if "not relevant" in plain_fb.lower():
                region = "global"
                strategy = STRATEGY_BROAD
            if "insufficient" in plain_fb.lower():
                region = "global"
                search_looseness = "broad"
                strategy = STRATEGY_BROAD
            if "no signals" in plain_fb.lower():
                industry = "AI"
                strategy = STRATEGY_SIGNAL
            confidence = round(max(0.3, 0.6 - retry_count * 0.1), 2)
            strategy = STRATEGY_FEEDBACK

        return {
            "entity_type": "companies",
            "filters": {
                "industry": industry,
                "region": region,
                "keywords": keywords,
            },
            "tasks": ["search", "enrich", "rank", "analyze", "generate_outreach"],
            "strategy": strategy,
            "search_looseness": search_looseness,
            "confidence": confidence,
            "critic_feedback_applied": structured_fb.get("error") or (plain_fb or None),
        }

    # ── Extraction helpers 

    def _extract_industry(self, query_lower: str) -> str:
        if any(w in query_lower for w in ["fintech", "finance", "banking", "payments"]):
            return "fintech"
        if any(w in query_lower for w in ["health", "medical", "biotech", "healthcare"]):
            return "health"
        if any(w in query_lower for w in ["saas", "software", "cloud"]):
            return "saas"
        return "AI"

    def _extract_region(self, query_lower: str) -> str:
        if any(w in query_lower for w in ["us", "united states", "america"]):
            return "US"
        if any(w in query_lower for w in ["europe", "eu", "european"]):
            return "EU"
        if any(w in query_lower for w in ["uk", "united kingdom", "britain"]):
            return "UK"
        return "global"

    def _extract_keywords(self, query_lower: str) -> List[str]:
        stop = {"find", "give", "show", "get", "list", "with", "that", "from",
                "into", "this", "have", "will", "they", "what", "which", "companies",
                "company", "startups", "startup", "and", "for", "the", "their"}
        words = [w for w in query_lower.split() if len(w) > 3 and w not in stop]
        return words[:6]

    def _fallback_plan(self, query: str) -> Dict[str, Any]:
        return {
            "entity_type": "companies",
            "filters": {"industry": "AI", "region": "global", "keywords": [query]},
            "tasks": ["search", "enrich", "rank"],
            "strategy": STRATEGY_FALLBACK,
            "search_looseness": "broad",
            "confidence": 0.3,
            "critic_feedback_applied": None,
        }