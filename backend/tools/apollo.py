"""
Apollo.io enrichment client (simulated).
Adds LinkedIn URL, revenue estimate, tech maturity, and job posting signals.
"""

import logging

logger = logging.getLogger("gtm.tools.apollo")

REVENUE_BY_STAGE = {
    "Seed":     "< $1M",
    "Series A": "$1M–$5M",
    "Series B": "$5M–$20M",
    "Series C": "$20M–$60M",
    "Series D": "$60M–$150M",
    "Series E": "$150M–$400M",
    "Series F": "$400M–$1B",
    "Series G": "$1B+",
    "Late Stage": "$500M+",
    "Public":   "$1B+",
}

TECH_MATURITY_BY_SIZE = {
    (0,    100):  "early",
    (101,  500):  "mid",
    (501,  2000): "scaling",
    (2001, 99999):"enterprise",
}


class ApolloClient:
    """
    Simulates Apollo.io people + company enrichment.
    In production: replace _enrich_one() with a real Apollo REST call.
    """

    def enrich(self, data: list) -> list:
        enriched = []
        for item in data:
            try:
                enriched.append(self._enrich_one(item))
            except Exception as e:
                logger.warning(f"apollo enrich failed for {item.get('company')}: {e}")
                enriched.append(item)
        logger.info(f"apollo enriched {len(enriched)} records")
        return enriched

    def _enrich_one(self, item: dict) -> dict:
        item = item.copy()
        company = item.get("company", "unknown").lower().replace(" ", "-")
        employees = item.get("employees", 0)
        funding = item.get("funding", "")

        # LinkedIn URL
        item["linkedin_url"] = f"https://linkedin.com/company/{company}"

        # Revenue estimate from funding stage
        item["revenue_estimate"] = REVENUE_BY_STAGE.get(funding, "Unknown")

        # Tech maturity from headcount
        item["tech_maturity"] = self._maturity(employees)

        # Apollo-style job posting signal
        item["open_roles"] = self._infer_open_roles(item)

        # Buying intent tier
        item["apollo_intent_score"] = self._intent_score(item)

        return item

    def _maturity(self, employees: int) -> str:
        for (low, high), label in TECH_MATURITY_BY_SIZE.items():
            if low <= employees <= high:
                return label
        return "unknown"

    def _infer_open_roles(self, item: dict) -> list:
        roles = []
        signals = item.get("signals", [])
        if "hiring_aggressively" in signals:
            roles += ["Account Executive", "SDR", "RevOps Manager"]
        if "growth_funding" in signals:
            roles += ["VP Sales", "Head of Marketing"]
        if "enterprise_scale" in signals:
            roles += ["Enterprise AE", "Solutions Engineer"]
        return roles

    def _intent_score(self, item: dict) -> float:
        score = 0.3
        signals = item.get("signals", [])
        if "growth_funding"       in signals: score += 0.3
        if "hiring_aggressively"  in signals: score += 0.2
        if "mid_market_growth"    in signals: score += 0.1
        if "enterprise_scale"     in signals: score += 0.1
        return round(min(score, 1.0), 2)