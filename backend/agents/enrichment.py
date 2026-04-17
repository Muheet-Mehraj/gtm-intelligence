import logging
from typing import Dict, Any, List

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.enrichment")


class EnrichmentAgent:
    """
    Transforms raw data into enriched signals and insights.
    """

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("enrichment started")

        try:
            raw = state.raw_results or []

            enriched: List[Dict[str, Any]] = []
            signals: List[str] = []

            for record in raw:
                enriched_record = self._enrich(record)

                if not enriched_record.get("company"):
                    continue

                enriched.append(enriched_record)
                signals.extend(enriched_record.get("signals", []))

            # remove duplicate signals
            state.signals = list(set(signals))
            state.enriched_results = enriched

            state.add_trace(f"enriched {len(enriched)} records")
            state.add_log(f"signals: {len(state.signals)}")

            return state

        except Exception as e:
            logger.error(f"enrichment error: {str(e)}")
            state.errors.append(str(e))
            state.enriched_results = []
            state.signals = []
            return state

    def _enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        company = record.get("company")
        employees = record.get("employees")
        funding = record.get("funding")

        signals: List[str] = []

        if employees:
            if employees > 1000:
                signals.append("enterprise_scale")
            elif employees > 200:
                signals.append("mid_market_growth")
            else:
                signals.append("early_stage_team")

        if funding:
            if "Seed" in funding:
                signals.append("early_funding")
            elif "Series" in funding:
                signals.append("growth_funding")
            elif "Late" in funding:
                signals.append("late_stage")

        insight = self._derive_insight(signals)
        confidence = self._compute_confidence(record, signals)
        icp_score = self._compute_icp_score(record, signals)

        return {
            "company": company,
            "industry": record.get("industry"),
            "region": record.get("region"),
            "employees": employees,
            "funding": funding,
            "signals": signals,
            "insight": insight,
            "confidence": confidence,
            "icp_score": icp_score,
            "why_this_result": self._why_this_result(record, signals),
        }

    def _derive_insight(self, signals: List[str]) -> str:
        if "growth_funding" in signals and "mid_market_growth" in signals:
            return "scaling team with strong outbound potential"

        if "early_funding" in signals:
            return "budget sensitive but open to tools"

        if "late_stage" in signals:
            return "focus on optimization and vendor consolidation"

        return "limited signal"

    def _compute_confidence(self, record: Dict[str, Any], signals: List[str]) -> float:
        score = 0.5

        if record.get("employees"):
            score += 0.2

        if record.get("funding"):
            score += 0.2

        score += min(len(signals) * 0.05, 0.1)

        return round(min(score, 1.0), 2)

    def _compute_icp_score(self, record: Dict[str, Any], signals: List[str]) -> float:
        score = 0.0

        if "growth_funding" in signals:
            score += 0.4

        if "mid_market_growth" in signals:
            score += 0.3

        if record.get("employees") and record["employees"] > 200:
            score += 0.2

        if "enterprise_scale" in signals:
            score += 0.1

        return round(min(score, 1.0), 2)
    
    def _why_this_result(self, record: Dict[str, Any], signals: List[str]) -> str:
        reasons = []
    

        employees = record.get("employees", 0)
        funding = record.get("funding", "")

        if "growth_funding" in signals:
            reasons.append(f"{funding} indicates growth phase")

        if "mid_market_growth" in signals:
            reasons.append(f"{employees} employees suggests scaling outbound")

        if "enterprise_scale" in signals:
            reasons.append("enterprise scale implies high deal volume")

        if "early_stage_team" in signals:
            reasons.append("early-stage team likely experimenting with GTM")

        if not reasons:
            return "limited signals available — exploratory opportunity"

        return " + ".join(reasons)