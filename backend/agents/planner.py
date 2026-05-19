import json
import logging
import os
import re
import time
from typing import Dict, Any, List

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.planner")

STRATEGY_BROAD    = "broad_search"
STRATEGY_NICHE    = "niche_focus"
STRATEGY_SIGNAL   = "signal_driven"
STRATEGY_FALLBACK = "fallback_planning"
STRATEGY_FEEDBACK = "feedback_adjusted_planning"

VALID_STRATEGIES = {STRATEGY_BROAD, STRATEGY_NICHE, STRATEGY_SIGNAL, STRATEGY_FALLBACK, STRATEGY_FEEDBACK}

PLANNER_SYSTEM_PROMPT = """You are a GTM pipeline planner. Your job is to convert a natural language ICP query into a structured execution plan.

You will receive:
- The user's original query
- Critic feedback from the previous attempt (if this is a retry)
- The current retry count

You must return a JSON object with this exact schema:
{
  "entity_type": "companies",
  "filters": {
    "industry": "<one of: AI, fintech, health, saas, or the most relevant industry>",
    "region": "<one of: US, EU, UK, global>",
    "keywords": ["<3-6 short keywords derived from the query>"]
  },
  "tasks": ["search", "enrich", "rank", "analyze", "generate_outreach"],
  "strategy": "<one of: broad_search, niche_focus, signal_driven, feedback_adjusted_planning>",
  "search_looseness": "<strict or broad>",
  "confidence": <0.0 to 1.0>,
  "critic_feedback_applied": "<error code from critic or null>"
}

Strategy rules:
- signal_driven: query mentions hiring, funding, growth signals
- niche_focus: specific industry or region mentioned
- broad_search: vague query or retry after empty/insufficient results
- feedback_adjusted_planning: retry with critic feedback applied

search_looseness rules:
- strict: first attempt or well-defined query
- broad: any retry, or query is vague

confidence rules:
- Start at 0.75 for a clear query, lower for vague queries
- Reduce by 0.1 per retry cycle
- Never below 0.2

On retries, apply the critic's suggested adjustments — do not ignore them.

Return ONLY the JSON object. No preamble, no markdown fences."""


class PlannerAgent:
    """
    Converts user query into a structured execution plan.
    Primary path: Groq LLM (llama-3.3-70b-versatile)
    Fallback: heuristic extraction if Groq is unavailable or returns unparseable output
    On retries, consumes structured critic feedback to adapt:
      - strategy mode
      - industry + region filters
      - keywords
      - search_looseness
      - confidence
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
                logger.warning("planner: GROQ_API_KEY not set — will use heuristic fallback")
        except ImportError:
            logger.warning("planner: groq package not installed — will use heuristic fallback")

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("planner started")

        try:
            structured_fb = state.memory.get("critic_structured_feedback", {})
            plain_fb      = state.memory.get("critic_feedback", "")

            if self._groq_client:
                plan = self._llm_plan(state.query, structured_fb, plain_fb, state.retry_count)
            else:
                logger.info("planner: using heuristic fallback")
                plan = self._heuristic_plan(state.query, structured_fb, plain_fb, state.retry_count)

            state.plan = plan

            if structured_fb or plain_fb:
                error_code = structured_fb.get("error", "unknown")
                state.add_trace(
                    f"planner re-planned [attempt {state.retry_count + 1}] "
                    f"using critic feedback [{error_code}]: {plan['strategy']}, "
                    f"industry={plan['filters']['industry']}, "
                    f"region={plan['filters']['region']}, "
                    f"looseness={plan.get('search_looseness', 'strict')}"
                )
            else:
                state.add_trace(
                    f"planner created execution plan: "
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

    def _llm_plan(
        self,
        query: str,
        structured_fb: Dict[str, Any],
        plain_fb: str,
        retry_count: int,
    ) -> Dict[str, Any]:
        t0 = time.time()

        critic_context = ""
        if structured_fb:
            critic_context = f"""
Critic feedback from previous attempt:
- error: {structured_fb.get('error')}
- suggestion: {structured_fb.get('suggestion')}
- confidence: {structured_fb.get('confidence')}
- suggested adjustments: {json.dumps(structured_fb.get('adjust', {}))}
"""
        elif plain_fb:
            critic_context = f"\nCritic feedback: {plain_fb}"

        user_message = f"""Query: "{query}"
Retry count: {retry_count}
{critic_context}
Generate the execution plan."""

        try:
            response = self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                temperature=0.1,
                max_tokens=400,
            )

            latency  = round(time.time() - t0, 2)
            raw_text = response.choices[0].message.content.strip()
            usage    = response.usage

            logger.info(
                f"planner LLM: {latency}s | "
                f"tokens in={usage.prompt_tokens} out={usage.completion_tokens}"
            )

            state_metrics = {
                "source":     "groq/llama-3.3-70b-versatile",
                "latency_s":  latency,
                "tokens_in":  usage.prompt_tokens,
                "tokens_out": usage.completion_tokens,
            }
            # stored externally — caller must pass state if needed; log only here
            logger.debug(f"planner metrics: {state_metrics}")

            parsed = self._parse_llm_response(raw_text)
            if parsed is None:
                logger.warning("planner: LLM response unparseable — falling back to heuristics")
                return self._heuristic_plan(query, structured_fb, plain_fb, retry_count)

            return self._validate_plan(parsed, query, structured_fb, retry_count)

        except Exception as e:
            logger.warning(f"planner: Groq call failed ({e}) — falling back to heuristics")
            return self._heuristic_plan(query, structured_fb, plain_fb, retry_count)

    def _parse_llm_response(self, text: str) -> Dict[str, Any] | None:
        text = re.sub(r"```json|```", "", text).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None

        required = {"entity_type", "filters", "tasks", "strategy", "search_looseness", "confidence"}
        if not required.issubset(data.keys()):
            logger.warning(f"planner: LLM response missing fields: {required - data.keys()}")
            return None

        if data.get("strategy") not in VALID_STRATEGIES:
            logger.warning(f"planner: invalid strategy '{data.get('strategy')}' — rejecting")
            return None

        return data

    def _validate_plan(
        self,
        plan: Dict[str, Any],
        query: str,
        structured_fb: Dict[str, Any],
        retry_count: int,
    ) -> Dict[str, Any]:
        """Sanity-check and clamp LLM output before it enters the pipeline."""
        filters = plan.get("filters", {})

        if not filters.get("industry"):
            filters["industry"] = self._extract_industry(query.lower())
        if not filters.get("region"):
            filters["region"] = self._extract_region(query.lower())
        if not filters.get("keywords"):
            filters["keywords"] = self._extract_keywords(query.lower())

        keywords = filters.get("keywords", [])
        if not isinstance(keywords, list):
            filters["keywords"] = self._extract_keywords(query.lower())
        else:
            filters["keywords"] = keywords[:6]

        plan["filters"] = filters

        confidence = plan.get("confidence", 0.75)
        plan["confidence"] = round(max(0.2, min(1.0, float(confidence))), 2)

        if plan.get("search_looseness") not in ("strict", "broad"):
            plan["search_looseness"] = "broad" if retry_count > 0 else "strict"

        if "critic_feedback_applied" not in plan:
            plan["critic_feedback_applied"] = structured_fb.get("error") if structured_fb else None

        if "tasks" not in plan or not plan["tasks"]:
            plan["tasks"] = ["search", "enrich", "rank", "analyze", "generate_outreach"]

        plan["entity_type"] = "companies"

        return plan

    def _heuristic_plan(
        self,
        query: str,
        structured_fb: Dict[str, Any],
        plain_fb: str,
        retry_count: int,
    ) -> Dict[str, Any]:
        query_lower = query.lower()

        industry = self._extract_industry(query_lower)
        region   = self._extract_region(query_lower)
        keywords = self._extract_keywords(query_lower)
        strategy = STRATEGY_NICHE if industry != "AI" else STRATEGY_SIGNAL
        search_looseness = "strict"
        confidence = 0.75

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
                "region":   region,
                "keywords": keywords,
            },
            "tasks":            ["search", "enrich", "rank", "analyze", "generate_outreach"],
            "strategy":         strategy,
            "search_looseness": search_looseness,
            "confidence":       confidence,
            "critic_feedback_applied": structured_fb.get("error") or (plain_fb or None),
        }

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
            "tasks":            ["search", "enrich", "rank"],
            "strategy":         STRATEGY_FALLBACK,
            "search_looseness": "broad",
            "confidence":       0.3,
            "critic_feedback_applied": None,
        }