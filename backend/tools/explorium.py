"""
Explorium data enrichment client (simulated).
Adds firmographic signals: growth trajectory, churn risk, and tech stack fit.
"""

import logging

logger = logging.getLogger("gtm.tools.explorium")

GROWTH_TRAJECTORY = {
    "Seed":     "pre-product-market-fit",
    "Series A": "early traction",
    "Series B": "scaling go-to-market",
    "Series C": "aggressive expansion",
    "Series D": "market leadership play",
    "Series E": "late hypergrowth",
    "Series F": "pre-IPO",
    "Series G": "pre-IPO / consolidation",
    "Late Stage": "mature / optimizing",
    "Public":   "public company",
}

CHURN_RISK_SIGNALS = {"churn_risk", "late_stage", "enterprise_scale"}
BUYING_SIGNALS     = {"growth_funding", "hiring_aggressively", "mid_market_growth"}


class ExploriumClient:
    """
    Simulates Explorium firmographic enrichment.
    In production: replace _search_one() with Explorium REST API call.
    """

    def search(self, query: str) -> list:
        """
        In production this would hit Explorium's search API.
        Returns empty here — retrieval agent uses its own mock dataset.
        Explorium is used for enrichment augmentation, not primary retrieval.
        """
        logger.info(f"explorium search called for: {query!r}")
        return []

    def enrich(self, data: list) -> list:
        enriched = []
        for item in data:
            try:
                enriched.append(self._enrich_one(item))
            except Exception as e:
                logger.warning(f"explorium enrich failed for {item.get('company')}: {e}")
                enriched.append(item)
        logger.info(f"explorium enriched {len(enriched)} records")
        return enriched

    def _enrich_one(self, item: dict) -> dict:
        item = item.copy()
        signals = set(item.get("signals", []))
        funding = item.get("funding", "")

        # Growth trajectory label
        item["growth_trajectory"] = GROWTH_TRAJECTORY.get(funding, "unknown")

        # Churn risk flag (is this company likely using / about to drop a tool?)
        item["churn_risk_flag"] = bool(signals & CHURN_RISK_SIGNALS)

        # Buying signal strength
        buying_hits = len(signals & BUYING_SIGNALS)
        item["buying_signal_strength"] = (
            "high" if buying_hits >= 2 else
            "medium" if buying_hits == 1 else
            "low"
        )

        # GTM fit score (explorium-style)
        item["explorium_fit_score"] = self._fit_score(item)

        return item

    def _fit_score(self, item: dict) -> float:
        score = 0.2
        signals = item.get("signals", [])
        employees = item.get("employees", 0)
        if "growth_funding"      in signals: score += 0.3
        if "hiring_aggressively" in signals: score += 0.2
        if employees > 100:                  score += 0.1
        if employees > 500:                  score += 0.1
        if item.get("churn_risk_flag"):      score += 0.1
        return round(min(score, 1.0), 2)