import logging
import os
import time
import json
from typing import Dict, Any, List

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.planner")

# Strategy modes
STRATEGY_BROAD       = "broad_search"
STRATEGY_NICHE       = "niche_focus"
STRATEGY_SIGNAL      = "signal_driven"
STRATEGY_FALLBACK    = "fallback_planning"
STRATEGY_FEEDBACK    = "feedback_adjusted_planning"

# Words that look meaningful but carry no filter signal
STOP_WORDS = {
    "find", "give", "show", "get", "list", "with", "that", "from",
    "into", "this", "have", "will", "they", "what", "which", "companies",
    "company", "startups", "startup", "and", "for", "the", "their",
    # Generic qualifiers that confuse the critic's relevance check
    "high", "growth", "high-growth", "top", "best", "leading", "major",
    "good", "great", "strong", "fast", "quickly", "scale", "scaling",
    "identify", "search", "looking", "want", "need", "please",
}

PLANNER_SYSTEM_PROMPT = """You are a GTM search planner. Convert the user's natural language query into a structured search plan.

Return ONLY a JSON object with this exact schema:
{
  "industry": "<one of: AI, saas, fintech, health, healthtech, enterprise>",
  "region": "<one of: US, EU, UK, global>",
  "keywords": ["<2-4 meaningful signal keywords, NO generic words like 'companies' or 'high-growth'>"],
  "strategy": "<one of: niche_focus, signal_driven, broad_search>",
  "search_looseness": "<strict or broad>",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<one sentence>"
}

Rules:
- keywords must be specific and signal-relevant (e.g. "outbound", "Series B", "hiring" — NOT "companies", "high-growth", "find")
- strategy = signal_driven when query mentions signals (hiring, churn, funding); niche_focus for specific verticals; broad_search for vague queries
- If the query mentions AI or SaaS companies, industry = AI
- Return ONLY the JSON object, no markdown, no preamble"""


class PlannerAgent:
    """
    Converts user query into a structured execution plan.
    Primary: Groq LLM (llama-3.1-70b-versatile) for true NL understanding.
    Fallback: heuristic extraction if Groq is unavailable.
    On retries, consumes structured critic feedback to adapt deeply.
    """

    def __init__(self):
        self._groq_client = None
        self._init_groq()

    def _init_groq(self):
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if api_key:
                self._groq_client = Groq(api_key=api_key)
                logger.info("planner: Groq client initialised")
            else:
                logger.warning("planner: GROQ_API_KEY not set — heuristic fallback active")
        except ImportError:
            logger.warning("planner: groq package not installed — heuristic fallback active")

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

    # ── Plan creation ─────────────────────────────────────────────────

    def _create_plan(
        self,
        query: str,
        structured_fb: Dict[str, Any],
        plain_fb: str,
        retry_count: int,
    ) -> Dict[str, Any]:
        query_lower = query.lower()

        # On first attempt with no feedback — try LLM first
        if not structured_fb and not plain_fb and self._groq_client:
            llm_plan = self._llm_plan(query, retry_count)
            if llm_plan:
                return llm_plan

        # Heuristic base extraction
        industry = self._extract_industry(query_lower)
        region   = self._extract_region(query_lower)
        keywords = self._extract_keywords(query_lower)
        strategy = STRATEGY_NICHE if industry != "AI" else STRATEGY_SIGNAL
        search_looseness = "strict"
        confidence = 0.75

        # ── Deep adaptation from structured critic feedback ────────────
        if structured_fb:
            error_code = structured_fb.get("error", "")
            adjust     = structured_fb.get("adjust", {})
            fb_conf    = structured_fb.get("confidence", 0.5)

            if "industry" in adjust:
                industry = adjust["industry"]
                logger.info(f"planner: industry adjusted to '{industry}' per critic")

            if "region" in adjust:
                region = adjust["region"]
                logger.info(f"planner: region adjusted to '{region}' per critic")

            if "search_looseness" in adjust:
                search_looseness = adjust["search_looseness"]

            if "keywords" in adjust:
                extra = adjust["keywords"]
                # Filter out generic words from critic-suggested keywords too
                extra = [k for k in extra if k not in STOP_WORDS and len(k) > 3]
                keywords = list(dict.fromkeys(extra + keywords))[:6]

            if error_code in ("empty_results", "insufficient_results"):
                strategy = STRATEGY_BROAD
                search_looseness = "broad"
                confidence = max(0.4, fb_conf)

            elif error_code in ("low_relevance",):
                strategy = STRATEGY_SIGNAL
                keywords = [k for k in keywords if len(k) > 5][:4]
                confidence = max(0.45, fb_conf)

            elif error_code in ("industry_mismatch", "region_mismatch"):
                strategy = STRATEGY_BROAD
                confidence = max(0.4, fb_conf)

            elif error_code in ("hallucinated_filter",):
                industry = self._extract_industry(query_lower)
                region   = self._extract_region(query_lower)
                strategy = STRATEGY_NICHE
                confidence = max(0.5, fb_conf)

            elif error_code in ("no_signals",):
                industry = "AI"
                strategy = STRATEGY_SIGNAL
                search_looseness = "broad"
                confidence = max(0.35, fb_conf)

            confidence = round(max(0.2, confidence - (retry_count * 0.1)), 2)

        elif plain_fb:
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
            "source": "heuristic",
        }

    # ── LLM planning via Groq ─────────────────────────────────────────

    def _llm_plan(self, query: str, retry_count: int) -> Dict[str, Any] | None:
        """Use Groq to parse the query into a structured plan."""
        t0 = time.time()
        try:
            response = self._groq_client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user",   "content": f'Query: "{query}"'},
                ],
                temperature=0.1,
                max_tokens=300,
            )

            latency  = round(time.time() - t0, 2)
            raw_text = response.choices[0].message.content.strip()
            usage    = response.usage

            logger.info(
                f"planner LLM: {latency}s | "
                f"tokens in={usage.prompt_tokens} out={usage.completion_tokens}"
            )

            parsed = self._parse_llm_plan(raw_text)
            if parsed is None:
                logger.warning("planner: LLM response unparseable — using heuristics")
                return None

            # Normalise into the standard plan shape
            plan = {
                "entity_type": "companies",
                "filters": {
                    "industry": parsed.get("industry", "AI"),
                    "region":   parsed.get("region", "global"),
                    "keywords": parsed.get("keywords", []),
                },
                "tasks": ["search", "enrich", "rank", "analyze", "generate_outreach"],
                "strategy":          parsed.get("strategy", STRATEGY_SIGNAL),
                "search_looseness":  parsed.get("search_looseness", "strict"),
                "confidence":        parsed.get("confidence", 0.75),
                "critic_feedback_applied": None,
                "source": "groq/llama-3.1-70b-versatile",
            }

            # Store metrics
            state_metrics = {
                "source":    "groq/llama-3.1-70b-versatile",
                "latency_s": latency,
                "tokens_in": usage.prompt_tokens,
                "tokens_out": usage.completion_tokens,
            }
            logger.info(f"planner LLM plan: {plan['filters']} | reasoning: {parsed.get('reasoning', '')}")
            return plan

        except Exception as e:
            logger.warning(f"planner: Groq call failed ({e}) — falling back to heuristics")
            return None

    def _parse_llm_plan(self, text: str) -> Dict[str, Any] | None:
        import re
        text = re.sub(r"```json|```", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    return None
            return None

    # ── Heuristic helpers ─────────────────────────────────────────────

    def _extract_industry(self, query_lower: str) -> str:
        if any(w in query_lower for w in ["fintech", "finance", "banking", "payments"]):
            return "fintech"
        if any(w in query_lower for w in ["health", "medical", "biotech", "healthcare"]):
            return "health"
        # "AI SaaS" or "AI" → AI (check AI first, SaaS alone → saas)
        if any(w in query_lower for w in ["ai", "artificial intelligence", "machine learning"]):
            return "AI"
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
        words = [
            w.strip("-").strip()
            for w in query_lower.split()
            if len(w) > 3 and w.strip("-") not in STOP_WORDS
        ]
        # Also deduplicate
        seen = set()
        result = []
        for w in words:
            if w not in seen:
                seen.add(w)
                result.append(w)
        return result[:5]

    def _fallback_plan(self, query: str) -> Dict[str, Any]:
        return {
            "entity_type": "companies",
            "filters": {"industry": "AI", "region": "global", "keywords": []},
            "tasks": ["search", "enrich", "rank"],
            "strategy": STRATEGY_FALLBACK,
            "search_looseness": "broad",
            "confidence": 0.3,
            "critic_feedback_applied": None,
            "source": "fallback",
        }