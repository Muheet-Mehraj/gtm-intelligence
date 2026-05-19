import json
import logging
import os
import random
import re
import time
from typing import List, Dict, Any

from backend.orchestrator.state import AgentState
from backend.tools.mcp_retrieval import MCPRetrievalTool

logger = logging.getLogger("gtm.retrieval")

REGION_ALIASES = {
    "eu":     ["eu", "europe", "european"],
    "europe": ["eu", "europe", "european"],
    "us":     ["us", "usa", "united states", "north america", "america"],
    "usa":    ["us", "usa", "united states", "north america"],
    "uk":     ["uk", "united kingdom", "britain"],
    "apac":   ["apac", "asia", "asia pacific"],
    "global": ["us", "eu", "uk", "apac", "global"],
}

INDUSTRY_ALIASES = {
    "ai":         ["ai", "artificial intelligence", "machine learning", "ml"],
    "saas":       ["saas", "software", "cloud"],
    "fintech":    ["fintech", "finance", "financial", "payments", "banking"],
    "health":     ["health", "healthtech", "healthcare", "medtech", "medical", "biotech"],
    "healthtech": ["health", "healthtech", "healthcare", "medtech"],
    "enterprise": ["enterprise", "saas", "software", "cloud"],
}

RETRIEVAL_SYSTEM_PROMPT = """You are a B2B market research analyst. Generate realistic company records that match the given search criteria.

Return ONLY a JSON object with this exact schema:
{
  "companies": [
    {
      "company": "<real or realistic company name>",
      "industry": "<exact industry from criteria>",
      "region": "<exact region from criteria>",
      "employees": <integer>,
      "funding": "<Seed | Series A | Series B | Series C | Series D | Series E | Series F | Series G | Late Stage | Public>",
      "hiring": <true | false>,
      "signals": ["<from: growth_funding, hiring_aggressively, mid_market_growth, enterprise_scale, early_stage_team, late_stage, churn_risk, high_intent>"],
      "tech_stack": ["<2-4 realistic technologies>"]
    }
  ]
}

Rules:
- Generate exactly 8 companies
- All companies must match the specified industry and region exactly
- Use real company names where possible, realistic fictional ones where needed
- Signals must reflect the company's actual stage and hiring status
- hiring_aggressively signal only if hiring is true and company is growing fast
- No preamble, no markdown fences"""


class ExternalAPIError(Exception):
    pass


class RetrievalAgent:
    """
    Fetches candidate companies based on planner output.

    Primary path: Groq LLM generates dynamic, query-specific company records
    Fallback: static mock dataset if Groq is unavailable or fails
    Also merges real signals from Gmail and Google Drive via MCP.

    Simulates real-world data quality issues:
      - partial or missing fields
      - schema inconsistencies
      - stale data
    """

    FAILURE_RATE = 0.0
    PARTIAL_RATE = 0.15

    def __init__(self):
        self.mcp = MCPRetrievalTool()
        self._groq_client = None
        self._init_groq()

    def _init_groq(self):
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if api_key:
                self._groq_client = Groq(api_key=api_key)
                logger.info("retrieval: Groq client initialised")
            else:
                logger.warning("retrieval: GROQ_API_KEY not set — will use static mock fallback")
        except ImportError:
            logger.warning("retrieval: groq package not installed — will use static mock fallback")

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("retrieval started")

        try:
            plan = state.plan or {}

            simulated_latency = random.uniform(0.05, 0.2)
            time.sleep(simulated_latency)
            state.add_trace(f"retrieval: data source responded in {simulated_latency:.2f}s")

            if random.random() < self.FAILURE_RATE and state.retry_count == 0:
                raise ExternalAPIError("data source timeout — connection refused (simulated)")

            if self._groq_client:
                results = self._llm_fetch(plan, state)
            else:
                results = self._fetch(plan, state)

            try:
                mcp_records = self.mcp.fetch(plan)
                if mcp_records:
                    existing_names = {r.get("company", "").lower() for r in results}
                    added = 0
                    for rec in mcp_records:
                        name = rec.get("company", "").lower()
                        if name and name not in existing_names:
                            results.append(rec)
                            existing_names.add(name)
                            added += 1
                    state.add_trace(f"MCP enrichment: +{added} records from Gmail/Drive (total: {len(results)})")
                else:
                    state.add_trace("MCP enrichment: no additional records from Gmail/Drive")
            except Exception as e:
                logger.warning(f"MCP retrieval skipped: {e}")
                state.add_trace(f"MCP retrieval unavailable: {str(e)[:80]}")

            results = self._inject_real_world_noise(results, state)
            clean, dropped = self._filter_corrupt(results)

            if dropped:
                state.add_trace(
                    f"retrieval: dropped {dropped} corrupt/partial records — "
                    f"{len(clean)} usable records remain"
                )

            state.raw_results = clean
            state.add_trace(f"retrieved {len(clean)} records (filtered + ranked)")
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

    def _llm_fetch(self, plan: Dict[str, Any], state: AgentState) -> List[Dict[str, Any]]:
        """Use Groq to generate dynamic company records matching the plan."""
        t0 = time.time()
        filters  = plan.get("filters", {})
        industry = filters.get("industry", "AI")
        region   = filters.get("region", "global")
        keywords = filters.get("keywords", [])
        strategy = plan.get("strategy", "signal_driven")
        looseness = plan.get("search_looseness", "strict")

        critic_fb = state.memory.get("critic_structured_feedback", {})
        retry_note = ""
        if critic_fb:
            retry_note = f"\nPrevious attempt failed with: {critic_fb.get('error')} — {critic_fb.get('suggestion')}"

        user_message = f"""Generate 8 companies matching these criteria:
- Industry: {industry}
- Region: {region}
- Keywords/signals to prioritize: {', '.join(keywords)}
- Strategy: {strategy}
- Search looseness: {looseness}
{retry_note}

Focus on companies that genuinely match the industry and region. Do not mix industries."""

        try:
            response = self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": RETRIEVAL_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                temperature=0.4,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            latency  = round(time.time() - t0, 2)
            raw_text = response.choices[0].message.content.strip()
            usage    = response.usage

            logger.info(
                f"retrieval LLM: {latency}s | "
                f"tokens in={usage.prompt_tokens} out={usage.completion_tokens}"
            )

            state.memory.setdefault("metrics", {})["retrieval"] = {
                "source":     "groq/llama-3.3-70b-versatile",
                "latency_s":  latency,
                "tokens_in":  usage.prompt_tokens,
                "tokens_out": usage.completion_tokens,
            }

            parsed = self._parse_llm_response(raw_text)
            if parsed:
                state.add_trace(f"retrieval LLM: generated {len(parsed)} companies for {industry}/{region}")
                return parsed

            logger.warning("retrieval LLM: unparseable response — falling back to static mock")
            state.add_trace("retrieval LLM: parse failed — using static mock fallback")
            return self._fetch(plan, state)

        except Exception as e:
            logger.warning(f"retrieval LLM: Groq call failed ({e}) — falling back to static mock")
            state.add_trace(f"retrieval LLM: failed ({str(e)[:60]}) — using static mock fallback")
            return self._fetch(plan, state)

    def _parse_llm_response(self, text: str) -> List[Dict[str, Any]] | None:
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

        companies = data.get("companies", [])
        if not isinstance(companies, list) or not companies:
            return None

        valid = []
        for c in companies:
            if (
                c.get("company")
                and c.get("industry")
                and c.get("region")
                and isinstance(c.get("employees"), int)
                and c["employees"] > 0
            ):
                c.setdefault("signals", [])
                c.setdefault("tech_stack", [])
                c.setdefault("hiring", False)
                valid.append(c)

        return valid if valid else None

    def _fetch(self, plan: Dict[str, Any], state: AgentState) -> List[Dict[str, Any]]:
        """Static mock fallback when Groq is unavailable."""
        filters  = plan.get("filters", {})
        industry = filters.get("industry", "").strip().lower()
        region   = filters.get("region", "global").strip().lower()
        keywords = [k.lower() for k in filters.get("keywords", [])]
        looseness = plan.get("search_looseness", "strict")

        data = self._mock_data()
        industry_variants = INDUSTRY_ALIASES.get(industry, [industry]) if industry else []
        region_variants   = REGION_ALIASES.get(region, [region])
        hard_filter       = looseness != "broad" and bool(industry_variants)
        scored_results    = []

        for item in data:
            score        = 0
            item_industry = item.get("industry", "").lower()
            item_region   = item.get("region", "").lower()

            if hard_filter and item_industry not in industry_variants:
                continue

            if industry_variants:
                if item_industry in industry_variants:
                    score += 3
                elif any(v in item_industry for v in industry_variants):
                    score += 2
                elif any(item_industry in v for v in industry_variants):
                    score += 1
                elif looseness == "broad":
                    score += 0.5
            else:
                score += 1

            if region == "global":
                score += 1
            elif item_region in region_variants:
                score += 3
            elif any(item_region in v for v in region_variants):
                score += 1
            elif looseness == "broad":
                score += 0.5

            item_str = str(item).lower()
            for kw in keywords:
                for word in kw.split():
                    if len(word) > 3 and word in item_str:
                        score += 1

            signals = item.get("signals", [])
            for kw in keywords:
                for sig in signals:
                    if any(word in sig for word in kw.split() if len(word) > 3):
                        score += 1

            if score > 1:
                item_copy = item.copy()
                item_copy["retrieval_score"] = round(score, 2)
                scored_results.append((score, item_copy))

        if not scored_results:
            logger.warning("no strict matches — trying soft fallback")
            state.add_trace("retrieval: strict match failed — activating soft fallback")
            for item in data:
                item_industry = item.get("industry", "").lower()
                item_region   = item.get("region", "").lower()
                soft_score    = 0
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

        if not scored_results:
            logger.warning("no fallback matches — returning diverse sample")
            state.add_trace("retrieval: fallback also failed — returning diverse industry sample")
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
        noisy       = []
        noise_count = 0

        for record in records:
            r = record.copy()

            if r.get("data_source") in ("gmail", "gdrive"):
                noisy.append(r)
                continue

            roll = random.random()
            if roll < self.PARTIAL_RATE:
                noise_count += 1
                noise_type = random.choice([
                    "missing_employees", "missing_funding", "schema_variant", "stale_data"
                ])
                if noise_type == "missing_employees":
                    r.pop("employees", None)
                    r["_data_issue"] = "employees_missing"
                elif noise_type == "missing_funding":
                    r.pop("funding", None)
                    r["_data_issue"] = "funding_missing"
                elif noise_type == "schema_variant":
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
        clean   = []
        dropped = 0

        for r in records:
            if "headcount" in r and "employees" not in r:
                r["employees"] = r.pop("headcount")

            has_company   = bool(r.get("company"))
            has_context   = bool(r.get("industry") or r.get("region"))
            has_employees = isinstance(r.get("employees"), int) and r["employees"] > 0
            is_mcp        = r.get("data_source") in ("gmail", "gdrive")

            if has_company and has_context and (has_employees or is_mcp):
                clean.append(r)
            else:
                dropped += 1
                logger.debug(f"dropped corrupt record: {r.get('company', 'unknown')}")

        return clean, dropped

    def _mock_data(self) -> List[Dict[str, Any]]:
        return [
            {"company": "ScaleAI",         "industry": "AI",        "region": "US", "employees": 800,  "funding": "Series E",  "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Kubernetes", "Snowflake"]},
            {"company": "OpenLayer",        "industry": "AI",        "region": "US", "employees": 120,  "funding": "Series A",  "hiring": True,  "signals": ["early_stage_team", "growth_funding"], "tech_stack": ["GCP", "Python", "dbt"]},
            {"company": "DataRobot",        "industry": "AI",        "region": "US", "employees": 2000, "funding": "Late Stage", "hiring": False, "signals": ["enterprise_scale", "late_stage"], "tech_stack": ["Azure", "Salesforce", "Tableau"]},
            {"company": "Cohere",           "industry": "AI",        "region": "US", "employees": 400,  "funding": "Series C",  "hiring": True,  "signals": ["growth_funding", "mid_market_growth", "hiring_aggressively"], "tech_stack": ["AWS", "Python", "Kubernetes"]},
            {"company": "Weights & Biases", "industry": "AI",        "region": "US", "employees": 350,  "funding": "Series C",  "hiring": True,  "signals": ["growth_funding", "mid_market_growth"], "tech_stack": ["GCP", "Python", "Kubernetes"]},
            {"company": "Hugging Face",     "industry": "AI",        "region": "US", "employees": 200,  "funding": "Series C",  "hiring": True,  "signals": ["growth_funding", "mid_market_growth", "hiring_aggressively"], "tech_stack": ["AWS", "PyTorch", "React"]},
            {"company": "Brex",             "industry": "fintech",   "region": "US", "employees": 1200, "funding": "Series D",  "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Snowflake", "Kafka"]},
            {"company": "Rippling",         "industry": "fintech",   "region": "US", "employees": 2000, "funding": "Series F",  "hiring": True,  "signals": ["enterprise_scale", "late_stage", "hiring_aggressively"], "tech_stack": ["Salesforce", "AWS", "Workday"]},
            {"company": "Carta",            "industry": "fintech",   "region": "US", "employees": 1500, "funding": "Series G",  "hiring": False, "signals": ["enterprise_scale", "late_stage"], "tech_stack": ["AWS", "Salesforce", "PostgreSQL"]},
            {"company": "Mercury",          "industry": "fintech",   "region": "US", "employees": 500,  "funding": "Series B",  "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Plaid", "Stripe"]},
            {"company": "Monzo",            "industry": "fintech",   "region": "EU", "employees": 2500, "funding": "Late Stage", "hiring": True,  "signals": ["enterprise_scale", "late_stage", "hiring_aggressively"], "tech_stack": ["GCP", "Kafka", "Go"]},
            {"company": "Revolut",          "industry": "fintech",   "region": "EU", "employees": 8000, "funding": "Late Stage", "hiring": True,  "signals": ["enterprise_scale", "late_stage", "hiring_aggressively"], "tech_stack": ["AWS", "Kafka", "Kubernetes"]},
            {"company": "Wise",             "industry": "fintech",   "region": "EU", "employees": 4000, "funding": "Public",    "hiring": True,  "signals": ["enterprise_scale", "late_stage"], "tech_stack": ["AWS", "Java", "Kubernetes"]},
            {"company": "SumUp",            "industry": "fintech",   "region": "EU", "employees": 3000, "funding": "Series F",  "hiring": True,  "signals": ["enterprise_scale", "growth_funding", "hiring_aggressively"], "tech_stack": ["GCP", "React", "Kotlin"]},
            {"company": "HealthSync",       "industry": "health",    "region": "EU", "employees": 150,  "funding": "Series A",  "hiring": True,  "signals": ["growth_funding", "mid_market_growth", "hiring_aggressively"], "tech_stack": ["Azure", "HL7 FHIR", "Python"]},
            {"company": "Kry",              "industry": "healthtech", "region": "EU", "employees": 700,  "funding": "Series D",  "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["GCP", "React Native", "Python"]},
            {"company": "Alan",             "industry": "healthtech", "region": "EU", "employees": 550,  "funding": "Series E",  "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Python", "PostgreSQL"]},
            {"company": "Ro",               "industry": "health",    "region": "US", "employees": 1000, "funding": "Series D",  "hiring": True,  "signals": ["mid_market_growth", "growth_funding", "hiring_aggressively"], "tech_stack": ["AWS", "Salesforce", "React"]},
            {"company": "Outreach",         "industry": "saas",      "region": "US", "employees": 1200, "funding": "Series G",  "hiring": False, "signals": ["late_stage", "enterprise_scale", "churn_risk"], "tech_stack": ["Salesforce", "AWS", "Snowflake"]},
            {"company": "Salesloft",        "industry": "saas",      "region": "US", "employees": 900,  "funding": "Series D",  "hiring": False, "signals": ["late_stage", "enterprise_scale", "churn_risk"], "tech_stack": ["Salesforce", "AWS", "HubSpot"]},
        ]