import json
import logging
import os
import re
import time
from typing import Dict, Any, List

from backend.orchestrator.state import AgentState
from backend.tools.apollo import ApolloClient
from backend.tools.explorium import ExploriumClient
from backend.tools.scoring import score_company

logger = logging.getLogger("gtm.enrichment")

ENRICHMENT_SYSTEM_PROMPT = """You are a GTM enrichment analyst. Given a company's data and detected signals, generate two things:

1. insight: a single concise sentence summarising why this company is an interesting GTM target right now
2. why_this_result: a short explanation (max 2 sentences) of what specific data points make this company a strong ICP match

You will receive a JSON object with company fields: name, industry, region, employees, funding, tech_stack, signals, apollo_intent_score, growth_trajectory, churn_risk_flag, explorium_fit_score.

Return ONLY a JSON object with this exact schema:
{
  "insight": "<one sentence>",
  "why_this_result": "<one to two sentences>"
}

Be specific — reference actual signals, funding stage, headcount, or tech stack where relevant.
No preamble, no markdown fences."""


class EnrichmentAgent:
    """
    Transforms raw data into enriched signals, insights, and ICP scores.

    Pipeline:
      1. Apollo enrichment: linkedin, revenue, intent score, open roles
      2. Explorium enrichment: growth trajectory, churn risk, buying signal strength
      3. Signal detection: from raw and enriched fields
      4. ICP scoring: via scoring.score_company()
      5. Insight and why_this_result: LLM-generated (Groq) or heuristic fallback
      6. Ranking: sort by icp_score descending
    """

    def __init__(self):
        self.apollo    = ApolloClient()
        self.explorium = ExploriumClient()
        self._groq_client = None
        self._init_groq()

    def _init_groq(self):
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if api_key:
                self._groq_client = Groq(api_key=api_key)
                logger.info("enrichment: Groq client initialised")
            else:
                logger.warning("enrichment: GROQ_API_KEY not set — will use heuristic fallback")
        except ImportError:
            logger.warning("enrichment: groq package not installed — will use heuristic fallback")

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("enrichment started")

        try:
            raw = state.raw_results or []
            if not raw:
                state.enriched_results = []
                state.signals = []
                state.add_trace("enrichment: no raw records to enrich")
                return state

            try:
                raw = self.apollo.enrich(raw)
                state.add_trace(f"enrichment: apollo added linkedin, revenue, intent scores for {len(raw)} records")
            except Exception as e:
                logger.warning(f"apollo enrichment failed: {e} — continuing without it")
                state.add_trace(f"enrichment: apollo unavailable ({e}) — skipping")

            try:
                raw = self.explorium.enrich(raw)
                state.add_trace(f"enrichment: explorium added growth trajectory + churn signals for {len(raw)} records")
            except Exception as e:
                logger.warning(f"explorium enrichment failed: {e} — continuing without it")
                state.add_trace(f"enrichment: explorium unavailable ({e}) — skipping")

            enriched: List[Dict[str, Any]] = []
            all_signals: List[str] = []

            for record in raw:
                enriched_record = self._enrich(record)
                if not enriched_record.get("company"):
                    continue
                enriched.append(enriched_record)
                all_signals.extend(enriched_record.get("signals", []))

            if self._groq_client and enriched:
                enriched = self._llm_enrich_batch(enriched)

            enriched = sorted(enriched, key=lambda x: x.get("icp_score", 0), reverse=True)
            state.add_trace(
                f"enrichment: ranked {len(enriched)} records by ICP score — "
                f"top: {enriched[0]['company']} ({enriched[0]['icp_score']:.2f}) "
                f"→ bottom: {enriched[-1]['company']} ({enriched[-1]['icp_score']:.2f})"
                if enriched else "enrichment: no records to rank"
            )

            state.signals = list(set(all_signals))
            state.enriched_results = enriched

            state.add_trace(
                f"enriched {len(enriched)} records — "
                f"{len(state.signals)} unique signals detected: {', '.join(sorted(state.signals))}"
            )
            state.add_log(f"signals: {len(state.signals)}")
            return state

        except Exception as e:
            logger.error(f"enrichment error: {str(e)}")
            state.errors.append(str(e))
            state.add_trace(f"enrichment failed: {str(e)}")
            state.enriched_results = []
            state.signals = []
            return state

    def _llm_enrich_batch(self, enriched: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Call Groq once per record to generate LLM insight and why_this_result.
        Falls back to heuristic values per record if the LLM call fails.
        """
        t0 = time.time()
        success_count = 0

        for record in enriched:
            try:
                payload = {
                    "name":               record.get("company"),
                    "industry":           record.get("industry"),
                    "region":             record.get("region"),
                    "employees":          record.get("employees"),
                    "funding":            record.get("funding"),
                    "tech_stack":         record.get("tech_stack", []),
                    "signals":            record.get("signals", []),
                    "apollo_intent_score":record.get("apollo_intent_score", 0),
                    "growth_trajectory":  record.get("growth_trajectory"),
                    "churn_risk_flag":    record.get("churn_risk_flag", False),
                    "explorium_fit_score":record.get("explorium_fit_score", 0),
                }

                response = self._groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                        {"role": "user",   "content": json.dumps(payload)},
                    ],
                    temperature=0.2,
                    max_tokens=200,
                )

                raw_text = response.choices[0].message.content.strip()
                parsed   = self._parse_llm_response(raw_text)

                if parsed:
                    record["insight"]         = parsed.get("insight", record["insight"])
                    record["why_this_result"] = parsed.get("why_this_result", record["why_this_result"])
                    success_count += 1
                else:
                    logger.warning(f"enrichment LLM: unparseable response for {record.get('company')} — keeping heuristic")

            except Exception as e:
                logger.warning(f"enrichment LLM: failed for {record.get('company')} ({e}) — keeping heuristic")

        latency = round(time.time() - t0, 2)
        logger.info(f"enrichment LLM: {success_count}/{len(enriched)} records enriched in {latency}s")

        return enriched

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

        if "insight" not in data or "why_this_result" not in data:
            return None

        return data

    def _enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        company   = record.get("company")
        employees = record.get("employees")
        funding   = record.get("funding")
        tech      = record.get("tech_stack", [])

        signals = list(record.get("signals", []))

        if employees:
            if employees > 1000 and "enterprise_scale" not in signals:
                signals.append("enterprise_scale")
            elif 200 < employees <= 1000 and "mid_market_growth" not in signals:
                signals.append("mid_market_growth")
            elif employees <= 200 and "early_stage_team" not in signals:
                signals.append("early_stage_team")

        if funding:
            if "Seed" in funding and "early_funding" not in signals:
                signals.append("early_funding")
            elif "Series" in funding and "growth_funding" not in signals:
                signals.append("growth_funding")
            elif "Late" in funding and "late_stage" not in signals:
                signals.append("late_stage")

        if record.get("apollo_intent_score", 0) > 0.7:
            signals.append("high_intent")

        if record.get("churn_risk_flag") and "churn_risk" not in signals:
            signals.append("churn_risk")

        signals = list(dict.fromkeys(signals))

        record_for_scoring = dict(record, signals=signals)
        icp_score  = score_company(record_for_scoring)
        confidence = self._compute_confidence(record, signals)

        # Heuristic fallbacks — overwritten per record if LLM succeeds
        insight    = self._derive_insight(signals, tech, funding)
        why_result = self._why_this_result(record, signals)

        return {
            "company":         company,
            "industry":        record.get("industry"),
            "region":          record.get("region"),
            "employees":       employees,
            "funding":         funding,
            "tech_stack":      tech,
            "signals":         signals,
            "insight":         insight,
            "confidence":      confidence,
            "icp_score":       icp_score,
            "why_this_result": why_result,
            "linkedin_url":           record.get("linkedin_url"),
            "revenue_estimate":       record.get("revenue_estimate"),
            "tech_maturity":          record.get("tech_maturity"),
            "open_roles":             record.get("open_roles", []),
            "apollo_intent_score":    record.get("apollo_intent_score", 0),
            "growth_trajectory":      record.get("growth_trajectory"),
            "churn_risk_flag":        record.get("churn_risk_flag", False),
            "buying_signal_strength": record.get("buying_signal_strength", "low"),
            "explorium_fit_score":    record.get("explorium_fit_score", 0),
        }

    def _derive_insight(self, signals: List[str], tech: List[str], funding: str) -> str:
        if "growth_funding" in signals and "hiring_aggressively" in signals:
            infra = [t for t in tech if t in ("AWS", "GCP", "Azure")]
            return (
                f"scaling team post-{funding} with strong outbound potential"
                + (f" — infra on {infra[0]}" if infra else "")
            )
        if "growth_funding" in signals and "mid_market_growth" in signals:
            return "scaling team with strong outbound potential"
        if "enterprise_scale" in signals and "churn_risk" in signals:
            return "enterprise at vendor consolidation stage — displacement opportunity"
        if "early_funding" in signals:
            return "budget-sensitive but actively evaluating tools post-raise"
        if "late_stage" in signals:
            return "focus on optimisation and vendor consolidation at scale"
        if "churn_risk" in signals:
            return "showing vendor fatigue — open to stack consolidation"
        return "limited signal — early exploratory opportunity"

    def _compute_confidence(self, record: Dict[str, Any], signals: List[str]) -> float:
        score = 0.4
        if record.get("employees"):  score += 0.2
        if record.get("funding"):    score += 0.2
        score += min(len(signals) * 0.04, 0.15)
        if record.get("apollo_intent_score", 0) > 0.5: score += 0.05
        if record.get("explorium_fit_score", 0) > 0.5: score += 0.05
        return round(min(score, 1.0), 2)

    def _why_this_result(self, record: Dict[str, Any], signals: List[str]) -> str:
        reasons = []
        funding   = record.get("funding", "")
        employees = record.get("employees", 0)
        tech      = record.get("tech_stack", [])

        if "growth_funding" in signals and funding:
            reasons.append(f"{funding} indicates active growth phase")
        if "hiring_aggressively" in signals and employees:
            reasons.append(f"{employees} headcount growing — SDR expansion likely")
        if "mid_market_growth" in signals:
            reasons.append("mid-market scale suggests outbound investment")
        if "enterprise_scale" in signals:
            reasons.append("enterprise size implies high deal volume")
        if "churn_risk" in signals:
            crm = [t for t in tech if t in ("Salesforce", "HubSpot", "Oracle")]
            reasons.append(
                f"running {crm[0]} with consolidation signals" if crm
                else "vendor consolidation signals detected"
            )
        if "early_stage_team" in signals:
            reasons.append("early-stage team likely evaluating GTM tools post-raise")
        if record.get("apollo_intent_score", 0) > 0.6:
            reasons.append(f"high Apollo intent score ({record['apollo_intent_score']:.2f})")

        return " + ".join(reasons) if reasons else "limited signals — exploratory opportunity"