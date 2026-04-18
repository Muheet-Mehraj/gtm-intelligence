import logging
from typing import Dict, Any, List
from backend.orchestrator.state import AgentState
from backend.tools.apollo import ApolloClient
from backend.tools.explorium import ExploriumClient
from backend.tools.scoring import score_company

logger = logging.getLogger("gtm.enrichment")


class EnrichmentAgent:
    """
    Transforms raw data into enriched signals, insights, and ICP scores.

    Pipeline:
      1. Apollo enrichment  — linkedin, revenue, intent score, open roles
      2. Explorium enrichment — growth trajectory, churn risk, buying signal strength
      3. Signal detection   — from raw + enriched fields
      4. ICP scoring        — via scoring.score_company() (uses all enriched fields)
      5. Insight generation — human-readable summary
      6. Ranking            — explicit sort by icp_score descending
    """

    def __init__(self):
        self.apollo    = ApolloClient()
        self.explorium = ExploriumClient()

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("enrichment started")

        try:
            raw = state.raw_results or []
            if not raw:
                state.enriched_results = []
                state.signals = []
                state.add_trace("enrichment: no raw records to enrich")
                return state

            # ── Step 1: Apollo enrichment 
            try:
                raw = self.apollo.enrich(raw)
                state.add_trace(f"enrichment: apollo added linkedin, revenue, intent scores for {len(raw)} records")
            except Exception as e:
                logger.warning(f"apollo enrichment failed: {e} — continuing without it")
                state.add_trace(f"enrichment: apollo unavailable ({e}) — skipping")

            # ── Step 2: Explorium enrichment 
            try:
                raw = self.explorium.enrich(raw)
                state.add_trace(f"enrichment: explorium added growth trajectory + churn signals for {len(raw)} records")
            except Exception as e:
                logger.warning(f"explorium enrichment failed: {e} — continuing without it")
                state.add_trace(f"enrichment: explorium unavailable ({e}) — skipping")

            # ── Steps 3–5: Signal detection, ICP scoring, insights 
            enriched: List[Dict[str, Any]] = []
            all_signals: List[str] = []

            for record in raw:
                enriched_record = self._enrich(record)
                if not enriched_record.get("company"):
                    continue
                enriched.append(enriched_record)
                all_signals.extend(enriched_record.get("signals", []))

            # ── Step 6: Explicit ranking by ICP score 
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

    def _enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        company   = record.get("company")
        employees = record.get("employees")
        funding   = record.get("funding")
        tech      = record.get("tech_stack", [])

        signals = list(record.get("signals", []))  # preserve signals from retrieval

        # Derive additional signals from enriched fields
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

        # Apollo-derived signals
        if record.get("apollo_intent_score", 0) > 0.7:
            signals.append("high_intent")

        # Explorium-derived signals
        if record.get("churn_risk_flag"):
            if "churn_risk" not in signals:
                signals.append("churn_risk")

        signals = list(dict.fromkeys(signals))  # deduplicate preserving order

        # ICP score via scoring tool (uses apollo + explorium fields too)
        record_for_scoring = dict(record, signals=signals)
        icp_score = score_company(record_for_scoring)

        confidence  = self._compute_confidence(record, signals)
        insight     = self._derive_insight(signals, tech, funding)
        why_result  = self._why_this_result(record, signals)

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
            # Pass-through enriched fields for GTM strategy use
            "linkedin_url":          record.get("linkedin_url"),
            "revenue_estimate":      record.get("revenue_estimate"),
            "tech_maturity":         record.get("tech_maturity"),
            "open_roles":            record.get("open_roles", []),
            "apollo_intent_score":   record.get("apollo_intent_score", 0),
            "growth_trajectory":     record.get("growth_trajectory"),
            "churn_risk_flag":       record.get("churn_risk_flag", False),
            "buying_signal_strength":record.get("buying_signal_strength", "low"),
            "explorium_fit_score":   record.get("explorium_fit_score", 0),
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