import json
import logging
import os
import time
from typing import Any, Dict, List

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.critic")

STOP_WORDS = {"find", "give", "show", "get", "list", "with", "that", "their",
              "from", "into", "this", "have", "will", "they", "what", "which"}

CRITIC_SYSTEM_PROMPT = """You are a GTM pipeline quality critic. Your job is to evaluate whether
enriched company records are relevant, high-quality, and grounded in the user's original query.

You will receive:
- The user's original query
- The planner's filters (industry, region, keywords)
- A list of enriched company records
- Detected signals

You must return a JSON object with this exact schema:
{
  "verdict": "PASS" | "RETRY" | "FAIL",
  "error": "<snake_case_error_code or null>",
  "suggestion": "<one sentence — what the planner should change on retry>",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<two sentences explaining your verdict>",
  "adjust": {
    "industry": "<corrected industry or null>",
    "region": "<corrected region or null>",
    "keywords": ["<keyword>"] or null,
    "search_looseness": "strict" | "broad" | null
  }
}

Verdict rules:
- PASS: results are relevant to the query, majority have required fields, signals are present
- RETRY: results are salvageable but off-target — suggest specific adjustments
- FAIL: pipeline exception or completely unrecoverable state

Error codes (use the most specific one):
- empty_results, insufficient_results, hallucinated_filter, industry_mismatch,
  region_mismatch, low_relevance, low_quality_data, no_signals

Return ONLY the JSON object. No preamble, no markdown fences."""


class CriticAgent:
    """
    Validates enriched results and decides: PASS | RETRY | FAIL

    Primary path: Groq LLM judge (llama-3.1-70b-versatile)
    Fallback: original heuristic checks if Groq is unavailable
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
                logger.info("critic: Groq client initialised")
            else:
                logger.warning("critic: GROQ_API_KEY not set — will use heuristic fallback")
        except ImportError:
            logger.warning("critic: groq package not installed — will use heuristic fallback")

    # ── Main entry point ──────────────────────────────────────────────

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

            # Try LLM judge first
            if self._groq_client:
                return self._llm_judge(state)

            # Fall back to heuristics
            logger.info("critic: using heuristic fallback")
            return self._heuristic_judge(state)

        except Exception as e:
            logger.error(f"critic error: {str(e)}")
            state.errors.append(str(e))
            return self._fail(state, f"critic exception: {str(e)}")

    # ── LLM judge ────────────────────────────────────────────────────

    def _llm_judge(self, state: AgentState) -> AgentState:
        """Calls Groq to evaluate the enriched results against the original query."""
        t0 = time.time()

        enriched   = state.enriched_results
        plan       = state.plan or {}
        filters    = plan.get("filters", {})

        # Build a compact summary of results (avoid huge token counts)
        result_summary = [
            {
                "company":   r.get("company"),
                "industry":  r.get("industry"),
                "region":    r.get("region"),
                "employees": r.get("employees"),
                "funding":   r.get("funding"),
                "signals":   r.get("signals", []),
                "icp_score": r.get("icp_score"),
                "confidence":r.get("confidence"),
            }
            for r in enriched[:8]  # cap at 8 records for token efficiency
        ]

        user_message = f"""Query: "{state.query}"

Planner filters applied:
- industry: {filters.get('industry', 'not set')}
- region: {filters.get('region', 'not set')}
- keywords: {filters.get('keywords', [])}
- strategy: {plan.get('strategy', 'not set')}
- retry_count: {state.retry_count}

Enriched results ({len(enriched)} records):
{json.dumps(result_summary, indent=2)}

Detected signals: {state.signals}

Evaluate these results and return your verdict as JSON."""

        try:
            response = self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                temperature=0.1,
                max_tokens=400,
            )

            latency   = round(time.time() - t0, 2)
            raw_text  = response.choices[0].message.content.strip()
            usage     = response.usage

            logger.info(
                f"critic LLM: {latency}s | "
                f"tokens in={usage.prompt_tokens} out={usage.completion_tokens}"
            )

            # Store metrics in state memory
            state.memory.setdefault("metrics", {})["critic"] = {
                "source":      "groq/llama-3.3-70b-versatile",
                "latency_s":   latency,
                "tokens_in":   usage.prompt_tokens,
                "tokens_out":  usage.completion_tokens,
            }

            parsed = self._parse_llm_response(raw_text)
            if parsed is None:
                logger.warning("critic: LLM response unparseable — falling back to heuristics")
                return self._heuristic_judge(state)

            return self._apply_verdict(state, parsed)

        except Exception as e:
            logger.warning(f"critic: Groq call failed ({e}) — falling back to heuristics")
            return self._heuristic_judge(state)

    def _parse_llm_response(self, text: str) -> Dict[str, Any] | None:
        """Parse the LLM's JSON response safely."""
        import re
        # Strip markdown fences if present
        text = re.sub(r"```json|```", "", text).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from surrounding text
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None

        # Validate required fields
        if "verdict" not in data or data["verdict"] not in ("PASS", "RETRY", "FAIL"):
            return None

        return data

    def _apply_verdict(self, state: AgentState, parsed: Dict[str, Any]) -> AgentState:
        """Route the parsed LLM verdict to the correct state transition."""
        verdict    = parsed.get("verdict", "RETRY")
        error      = parsed.get("error")
        suggestion = parsed.get("suggestion", "no suggestion provided")
        confidence = parsed.get("confidence", 0.5)
        reasoning  = parsed.get("reasoning", "")
        adjust     = parsed.get("adjust", {})

        # Clean None values from adjust
        adjust = {k: v for k, v in adjust.items() if v is not None}

        log_line = (
            f"critic LLM verdict: {verdict} "
            f"[{error or 'none'}] conf={confidence:.0%} — {reasoning}"
        )
        logger.info(log_line)
        state.add_trace(log_line)

        if verdict == "PASS":
            state.set_critic("PASS", suggestion or reasoning or "LLM judge: results approved")
            return state

        if verdict == "FAIL":
            return self._fail(state, suggestion)

        # RETRY
        return self._retry(state, {
            "error":      error or "llm_retry",
            "suggestion": suggestion,
            "confidence": confidence,
            "adjust":     adjust,
        })

    # ── Heuristic fallback ────────────────────────────────────────────

    def _heuristic_judge(self, state: AgentState) -> AgentState:
        """Original rule-based critic — used when Groq is unavailable."""
        enriched = state.enriched_results

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

        state.set_critic("PASS", "heuristic: relevance OK, quality OK, signals present")
        state.add_trace("critic heuristic passed")
        return state

    # ── Heuristic helpers ─────────────────────────────────────────────

    def _detect_hallucination(self, query: str, plan: Dict[str, Any]) -> str:
        query_lower = query.lower()
        filters  = plan.get("filters", {})
        industry = filters.get("industry", "").lower()
        region   = filters.get("region", "global").lower()

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
            return "region 'EU' not grounded in query"

        return ""

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

    def _detect_region_mismatch(self, query: str, data: List[Dict], plan: Dict) -> str:
        expected = plan.get("filters", {}).get("region", "global").lower()
        if expected == "global":
            return ""
        region_aliases = {"eu": ["eu", "europe"], "us": ["us", "usa"], "uk": ["uk"]}
        valid   = region_aliases.get(expected, [expected])
        matched = sum(1 for r in data if r.get("region", "").lower() in valid)
        if matched == 0:
            return f"0/{len(data)} results match expected region '{expected}'"
        return ""

    def _is_relevant(self, query: str, data: List[Dict]) -> bool:
        # Strip generic words that are never in record fields
        GENERIC = {
            "high", "growth", "high-growth", "fast", "top", "best", "leading",
            "companies", "company", "startups", "startup", "find", "show", "get",
            "identify", "scale", "scaling",
        }
        keywords = [
            w.strip("-")
            for w in query.lower().split()
            if len(w) > 3 and w not in STOP_WORDS and w.strip("-") not in GENERIC
        ]

        # If nothing meaningful remains after filtering, pass by default
        if not keywords:
            return True

        for record in data:
            # Check against industry, region, signals — not just raw string dump
            record_terms = set()
            record_terms.add(record.get("industry", "").lower())
            record_terms.add(record.get("region", "").lower())
            record_terms.update(s.lower() for s in record.get("signals", []))
            record_terms.update(t.lower() for t in record.get("tech_stack", []))

            full_text = str(record).lower()
            record_terms.add(full_text)

            matched = sum(
                1 for kw in keywords
                if any(kw in term for term in record_terms)
            )
            if matched >= max(1, len(keywords) // 2):
                return True
        return False

    def _extract_focus_keywords(self, query: str) -> List[str]:
        return [
            w for w in query.lower().split()
            if len(w) > 4 and w not in STOP_WORDS
        ][:4]

    def _has_low_quality(self, data: List[Dict]) -> bool:
        required = ["company", "industry", "region", "employees", "funding"]
        bad = sum(
            1 for record in data
            if any(not record.get(f) for f in required)
            or record.get("confidence") is None
        )
        return bad > len(data) / 2

    # ── Verdict helpers ───────────────────────────────────────────────

    def _retry(self, state: AgentState, feedback: Dict[str, Any]) -> AgentState:
        reason = feedback.get("suggestion", "unknown reason")
        logger.warning(f"critic RETRY: {feedback.get('error')} — {reason}")
        state.set_critic("RETRY", reason)
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