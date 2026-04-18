import logging
import random
import time
from typing import List, Dict, Any

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.retrieval")

REGION_ALIASES = {
    "eu": ["eu", "europe", "european"],
    "europe": ["eu", "europe", "european"],
    "us": ["us", "usa", "united states", "north america", "america"],
    "usa": ["us", "usa", "united states", "north america"],
    "uk": ["uk", "united kingdom", "britain"],
    "apac": ["apac", "asia", "asia pacific"],
    "global": ["us", "eu", "uk", "apac", "global"],
}

INDUSTRY_ALIASES = {
    "ai": ["ai", "artificial intelligence", "machine learning", "ml", "saas", "ai saas"],
    "saas": ["saas", "ai", "ai saas", "software", "cloud"],
    "fintech": ["fintech", "finance", "financial", "payments", "banking"],
    "health": ["health", "healthtech", "healthcare", "medtech", "medical", "biotech"],
    "healthtech": ["health", "healthtech", "healthcare", "medtech"],
    "enterprise": ["enterprise", "saas", "ai", "software", "cloud"],
}


class ExternalAPIError(Exception):
    """Simulates a transient failure from an external data source."""
    pass


class RetrievalAgent:
    """
    Fetches data based on planner output.
    Simulates real-world retrieval behaviour:
      - transient API failures (triggering critic retry)
      - partial / missing fields
      - inconsistent schemas
      - variable latency
      - noisy records that must be filtered
    """

    # Simulate failure rate: ~15% chance of transient API error
    FAILURE_RATE = 0.15
    # Simulate partial data rate: ~20% of records have missing fields
    PARTIAL_RATE = 0.20

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("retrieval started")

        try:
            plan = state.plan or {}

            # Simulate variable latency (real APIs have this)
            simulated_latency = random.uniform(0.05, 0.2)
            time.sleep(simulated_latency)
            state.add_trace(f"retrieval: data source responded in {simulated_latency:.2f}s")

            # Simulate transient API failure
            if random.random() < self.FAILURE_RATE and state.retry_count == 0:
                raise ExternalAPIError("data source timeout — connection refused (simulated)")

            results = self._fetch(plan, state)

            # Simulate schema noise: inject partial records
            results = self._inject_real_world_noise(results, state)

            # Filter out records too corrupted to use
            clean, dropped = self._filter_corrupt(results)
            if dropped:
                state.add_trace(
                    f"retrieval: dropped {dropped} corrupt/partial records — "
                    f"{len(clean)} usable records remain"
                )

            state.raw_results = clean
            state.add_trace(f"retrieved {len(clean)} records")
            state.add_log(f"raw_results: {len(state.raw_results)}")
            return state

        except ExternalAPIError as e:
            logger.warning(f"external API failure: {e}")
            state.errors.append(f"retrieval API error: {str(e)}")
            state.add_trace(f"retrieval failed: {str(e)} — critic will trigger retry")
            state.raw_results = []
            return state

        except Exception as e:
            logger.error(f"retrieval error: {str(e)}")
            state.errors.append(str(e))
            state.raw_results = []
            return state

    def _fetch(self, plan: Dict[str, Any], state: AgentState) -> List[Dict[str, Any]]:
        filters = plan.get("filters", {})
        industry = filters.get("industry", "").strip().lower()
        region = filters.get("region", "global").strip().lower()
        keywords = [k.lower() for k in filters.get("keywords", [])]

        # On retry: loosen filters based on critic guidance
        strategy = plan.get("strategy", "")
        looseness = plan.get("search_looseness", "strict")

        data = self._mock_data()
        scored_results = []

        industry_variants = INDUSTRY_ALIASES.get(industry, [industry]) if industry else []
        region_variants = REGION_ALIASES.get(region, [region])

        for item in data:
            score = 0
            item_industry = item.get("industry", "").lower()
            item_region = item.get("region", "").lower()

            # Industry matching
            if industry_variants:
                if item_industry in industry_variants:
                    score += 3
                elif any(v in item_industry for v in industry_variants):
                    score += 2
                elif any(item_industry in v for v in industry_variants):
                    score += 1
                elif looseness == "broad":
                    score += 0.5  # on retry: credit even weak matches
            else:
                score += 1

            # Region matching
            if region == "global":
                score += 1
            elif item_region in region_variants:
                score += 3
            elif any(item_region in v for v in region_variants):
                score += 1
            elif looseness == "broad":
                score += 0.5

            # Keyword boost
            item_str = str(item).lower()
            for kw in keywords:
                for word in kw.split():
                    if len(word) > 3 and word in item_str:
                        score += 1

            # Signal boost
            signals = item.get("signals", [])
            for kw in keywords:
                for sig in signals:
                    if any(word in sig for word in kw.split() if len(word) > 3):
                        score += 1

            threshold = 1 if looseness == "broad" else 1
            if score > threshold:
                item_copy = item.copy()
                item_copy["retrieval_score"] = round(score, 2)
                scored_results.append((score, item_copy))

        # Soft fallback
        if not scored_results:
            logger.warning("no strict matches — trying soft fallback")
            state.add_trace("retrieval: strict match failed — activating soft fallback")
            for item in data:
                item_industry = item.get("industry", "").lower()
                item_region = item.get("region", "").lower()
                soft_score = 0
                if industry_variants and item_industry in industry_variants:
                    soft_score += 2
                if region != "global" and item_region in region_variants:
                    soft_score += 2
                if soft_score > 0:
                    item_copy = item.copy()
                    item_copy["retrieval_score"] = soft_score
                    item_copy["_fallback"] = True
                    scored_results.append((soft_score, item_copy))
            scored_results.sort(key=lambda x: x[0], reverse=True)

        # Last resort diverse sample
        if not scored_results:
            logger.warning("no fallback matches — returning diverse sample")
            state.add_trace(
                "retrieval: fallback also failed — returning diverse industry sample "
                "(data freshness issue or overly narrow filters)"
            )
            seen_industries = set()
            diverse = []
            for item in data:
                ind = item.get("industry", "").lower()
                if ind not in seen_industries:
                    diverse.append(item)
                    seen_industries.add(ind)
                if len(diverse) >= 3:
                    break
            return diverse

        scored_results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_results[:8]]

    def _inject_real_world_noise(
        self, records: List[Dict[str, Any]], state: AgentState
    ) -> List[Dict[str, Any]]:
        """
        Simulate real-world data quality issues:
        - missing fields (incomplete API response)
        - inconsistent schema (different field names)
        - stale / zero employee count
        """
        noisy = []
        noise_count = 0

        for record in records:
            r = record.copy()
            roll = random.random()

            if roll < self.PARTIAL_RATE:
                noise_count += 1
                noise_type = random.choice(["missing_employees", "missing_funding",
                                            "schema_variant", "stale_data"])

                if noise_type == "missing_employees":
                    r.pop("employees", None)
                    r["_data_issue"] = "employees_missing"

                elif noise_type == "missing_funding":
                    r.pop("funding", None)
                    r["_data_issue"] = "funding_missing"

                elif noise_type == "schema_variant":
                    # Different field name (inconsistent schema from data provider)
                    if "employees" in r:
                        r["headcount"] = r.pop("employees")
                    r["_data_issue"] = "schema_variant"

                elif noise_type == "stale_data":
                    r["employees"] = 0
                    r["_data_issue"] = "stale_headcount"

            noisy.append(r)

        if noise_count:
            state.add_trace(
                f"retrieval: detected {noise_count} records with data quality issues "
                f"(missing fields / schema inconsistency / stale data)"
            )

        return noisy

    def _filter_corrupt(self, records: List[Dict[str, Any]]) -> tuple:
        """
        Normalise schema variants and drop records too broken to enrich.
        Returns (clean_records, dropped_count).
        """
        clean = []
        dropped = 0

        for r in records:
            # Normalise schema variant: headcount → employees
            if "headcount" in r and "employees" not in r:
                r["employees"] = r.pop("headcount")

            # Must have company name and at least one of: industry or region
            has_company = bool(r.get("company"))
            has_context = bool(r.get("industry") or r.get("region"))
            has_employees = isinstance(r.get("employees"), int) and r["employees"] > 0

            if has_company and has_context and has_employees:
                clean.append(r)
            else:
                dropped += 1
                logger.debug(f"dropped corrupt record: {r.get('company', 'unknown')}")

        return clean, dropped

    def _mock_data(self) -> List[Dict[str, Any]]:
        return [
            # ── AI / US ───────────────────────────────────────────────
            {"company": "ScaleAI",          "industry": "AI",       "region": "US", "employees": 800,  "funding": "Series E", "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Kubernetes", "Snowflake"]},
            {"company": "OpenLayer",         "industry": "AI",       "region": "US", "employees": 120,  "funding": "Series A", "hiring": True,  "signals": ["early_stage_team", "growth_funding"], "tech_stack": ["GCP", "Python", "dbt"]},
            {"company": "DataRobot",         "industry": "AI",       "region": "US", "employees": 2000, "funding": "Late Stage","hiring": False, "signals": ["enterprise_scale", "late_stage"], "tech_stack": ["Azure", "Salesforce", "Tableau"]},
            {"company": "Cohere",            "industry": "AI",       "region": "US", "employees": 400,  "funding": "Series C", "hiring": True,  "signals": ["growth_funding", "mid_market_growth", "hiring_aggressively"], "tech_stack": ["AWS", "Python", "Kubernetes"]},
            {"company": "Weights & Biases",  "industry": "AI",       "region": "US", "employees": 350,  "funding": "Series C", "hiring": True,  "signals": ["growth_funding", "mid_market_growth"], "tech_stack": ["GCP", "Python", "Kubernetes"]},
            {"company": "Hugging Face",      "industry": "AI",       "region": "US", "employees": 200,  "funding": "Series C", "hiring": True,  "signals": ["growth_funding", "mid_market_growth", "hiring_aggressively"], "tech_stack": ["AWS", "PyTorch", "React"]},
            # ── Fintech / US ──────────────────────────────────────────
            {"company": "Brex",              "industry": "fintech",  "region": "US", "employees": 1200, "funding": "Series D", "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Snowflake", "Kafka"]},
            {"company": "Rippling",          "industry": "fintech",  "region": "US", "employees": 2000, "funding": "Series F", "hiring": True,  "signals": ["enterprise_scale", "late_stage", "hiring_aggressively"], "tech_stack": ["Salesforce", "AWS", "Workday"]},
            {"company": "Carta",             "industry": "fintech",  "region": "US", "employees": 1500, "funding": "Series G", "hiring": False, "signals": ["enterprise_scale", "late_stage"], "tech_stack": ["AWS", "Salesforce", "PostgreSQL"]},
            {"company": "Mercury",           "industry": "fintech",  "region": "US", "employees": 500,  "funding": "Series B", "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Plaid", "Stripe"]},
            # ── Fintech / EU ──────────────────────────────────────────
            {"company": "Monzo",             "industry": "fintech",  "region": "EU", "employees": 2500, "funding": "Late Stage","hiring": True,  "signals": ["enterprise_scale", "late_stage", "hiring_aggressively"], "tech_stack": ["GCP", "Kafka", "Go"]},
            {"company": "Revolut",           "industry": "fintech",  "region": "EU", "employees": 8000, "funding": "Late Stage","hiring": True,  "signals": ["enterprise_scale", "late_stage", "hiring_aggressively"], "tech_stack": ["AWS", "Kafka", "Kubernetes"]},
            {"company": "Wise",              "industry": "fintech",  "region": "EU", "employees": 4000, "funding": "Public",   "hiring": True,  "signals": ["enterprise_scale", "late_stage"], "tech_stack": ["AWS", "Java", "Kubernetes"]},
            {"company": "SumUp",             "industry": "fintech",  "region": "EU", "employees": 3000, "funding": "Series F", "hiring": True,  "signals": ["enterprise_scale", "growth_funding", "hiring_aggressively"], "tech_stack": ["GCP", "React", "Kotlin"]},
            # ── Health / EU ───────────────────────────────────────────
            {"company": "HealthSync",        "industry": "health",   "region": "EU", "employees": 150,  "funding": "Series A", "hiring": True,  "signals": ["growth_funding", "mid_market_growth", "hiring_aggressively"], "tech_stack": ["Azure", "HL7 FHIR", "Python"]},
            {"company": "Kry",               "industry": "healthtech","region": "EU", "employees": 700,  "funding": "Series D", "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["GCP", "React Native", "Python"]},
            {"company": "Alan",              "industry": "healthtech","region": "EU", "employees": 550,  "funding": "Series E", "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Python", "PostgreSQL"]},
            {"company": "Doctolib",          "industry": "healthtech","region": "EU", "employees": 2800, "funding": "Late Stage","hiring": True,  "signals": ["enterprise_scale", "late_stage", "hiring_aggressively"], "tech_stack": ["AWS", "Ruby on Rails", "React"]},
            {"company": "Babylon Health",    "industry": "health",   "region": "EU", "employees": 2000, "funding": "Late Stage","hiring": False, "signals": ["enterprise_scale", "late_stage"], "tech_stack": ["GCP", "Python", "TensorFlow"]},
            # ── Health / US ───────────────────────────────────────────
            {"company": "Ro",                "industry": "health",   "region": "US", "employees": 1000, "funding": "Series D", "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Salesforce", "React"]},
            {"company": "Included Health",   "industry": "healthtech","region": "US", "employees": 1200, "funding": "Series E", "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Python", "Snowflake"]},
            {"company": "Cerebral",          "industry": "healthtech","region": "US", "employees": 4000, "funding": "Series C", "hiring": False, "signals": ["enterprise_scale", "growth_funding"], "tech_stack": ["AWS", "React", "PostgreSQL"]},
            # ── SaaS / churn signals ──────────────────────────────────
            {"company": "Outreach",          "industry": "saas",     "region": "US", "employees": 1200, "funding": "Series G", "hiring": False, "signals": ["late_stage", "enterprise_scale", "churn_risk"], "tech_stack": ["Salesforce", "AWS", "Snowflake"]},
            {"company": "Salesloft",         "industry": "saas",     "region": "US", "employees": 900,  "funding": "Series D", "hiring": False, "signals": ["late_stage", "enterprise_scale", "churn_risk"], "tech_stack": ["Salesforce", "AWS", "HubSpot"]},
            {"company": "ZoomInfo",          "industry": "saas",     "region": "US", "employees": 3500, "funding": "Public",   "hiring": False, "signals": ["enterprise_scale", "late_stage", "churn_risk"], "tech_stack": ["Salesforce", "AWS", "Oracle"]},
            {"company": "Apollo.io",         "industry": "saas",     "region": "US", "employees": 600,  "funding": "Series D", "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "churn_risk"], "tech_stack": ["AWS", "React", "PostgreSQL"]},
        ]