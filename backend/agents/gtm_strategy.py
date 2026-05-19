import json
import logging
import os
import re
import time
from typing import List, Dict, Any

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.strategy")

PERSONAS = ["vp_sales", "ceo", "cto"]

STRATEGY_SYSTEM_PROMPT = """You are a B2B GTM copywriter. Given enriched company data, generate a complete GTM strategy package.

You will receive a JSON object with: company, industry, region, employees, funding, tech_stack, signals, insight, why_this_result, apollo_intent_score, growth_trajectory, churn_risk_flag.

Return ONLY a JSON object with this exact schema:
{
  "hook": "<one sentence — specific observation about this company's current situation>",
  "angle": "<one sentence — the strategic reason to reach out now>",
  "email": "<cold email, 4-6 sentences, no subject line, signed Best>",
  "personas": {
    "vp_sales": {
      "persona": "VP of Sales",
      "pain_point": "<specific pain for this company's stage>",
      "value_prop": "<specific value prop>",
      "hook": "<opening line for VP Sales>",
      "cta": "<call to action>"
    },
    "ceo": {
      "persona": "CEO",
      "pain_point": "<specific pain>",
      "value_prop": "<specific value prop>",
      "hook": "<opening line for CEO>",
      "cta": "<call to action>"
    },
    "cto": {
      "persona": "CTO",
      "pain_point": "<specific pain>",
      "value_prop": "<specific value prop>",
      "hook": "<opening line for CTO>",
      "cta": "<call to action>"
    }
  },
  "competitive": {
    "likely_stack": "<comma-separated tools they likely use>",
    "positioning_strategy": "<one to two sentences on how to position>",
    "differentiation": "<one sentence on key differentiator>"
  }
}

Rules:
- Be specific — reference actual signals, funding stage, headcount, and tech stack
- No generic filler like "I hope this finds you well"
- Hook must reference a concrete recent event or signal for this company
- Email opener must reference the hook naturally
- No preamble, no markdown fences"""


class GTMStrategyAgent:
    """
    Converts enriched results into insight-driven GTM messaging.
    Primary path: Groq LLM (llama-3.3-70b-versatile) per company
    Fallback: heuristic generation if Groq is unavailable or fails per record
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
                logger.info("strategy: Groq client initialised")
            else:
                logger.warning("strategy: GROQ_API_KEY not set — will use heuristic fallback")
        except ImportError:
            logger.warning("strategy: groq package not installed — will use heuristic fallback")

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("strategy started")

        try:
            enriched = state.enriched_results or []
            hooks, angles, emails, personas, competitive = [], [], [], [], []

            for record in enriched:
                company = record.get("company")
                if not company:
                    continue

                if self._groq_client:
                    result = self._llm_strategy(record)
                else:
                    result = None

                if result:
                    hooks.append({"company": company, "hook": result["hook"]})
                    angles.append({"company": company, "angle": result["angle"]})
                    emails.append({"company": company, "email": result["email"]})
                    personas.append({"company": company, "personas": result["personas"]})
                    competitive.append({"company": company, "competitive": result["competitive"]})
                else:
                    signals  = record.get("signals", [])
                    insight  = record.get("insight", "")
                    industry = record.get("industry", "")
                    tech     = record.get("tech_stack", [])
                    funding  = record.get("funding", "")
                    employees = record.get("employees", 0)

                    hook  = self._generate_hook(company, signals, tech, funding, employees)
                    angle = self._generate_angle(signals, insight, tech, industry)
                    email = self._generate_email(company, hook, angle, signals, tech)

                    hooks.append({"company": company, "hook": hook})
                    angles.append({"company": company, "angle": angle})
                    emails.append({"company": company, "email": email})
                    personas.append({"company": company, "personas": self._generate_personas(company, signals, insight, industry, tech)})
                    competitive.append({"company": company, "competitive": self._generate_competitive(company, signals, industry, tech)})

            state.memory.setdefault("metrics", {})["gtm_strategy"] = {
                "source":            "groq/llama-3.3-70b-versatile",
                "records_processed": len(hooks),
            }
            state.gtm_strategy = {
                "hooks":                    hooks,
                "angles":                   angles,
                "email_snippets":           emails,
                "persona_targeting":        personas,
                "competitive_intelligence": competitive,
            }

            state.add_trace(f"generated strategy for {len(hooks)} companies")
            state.add_trace(f"multi-persona targeting generated for {len(personas)} companies")
            state.add_trace(f"competitive intelligence generated for {len(competitive)} companies")
            state.add_log("gtm strategy created")
            return state

        except Exception as e:
            logger.error(f"strategy error: {str(e)}")
            state.errors.append(str(e))
            state.gtm_strategy = {"hooks": [], "angles": [], "email_snippets": []}
            return state

    def _llm_strategy(self, record: Dict[str, Any]) -> Dict[str, Any] | None:
        
        t0 = time.time()

        payload = {
            "company":            record.get("company"),
            "industry":           record.get("industry"),
            "region":             record.get("region"),
            "employees":          record.get("employees"),
            "funding":            record.get("funding"),
            "tech_stack":         record.get("tech_stack", []),
            "signals":            record.get("signals", []),
            "insight":            record.get("insight", ""),
            "why_this_result":    record.get("why_this_result", ""),
            "apollo_intent_score":record.get("apollo_intent_score", 0),
            "growth_trajectory":  record.get("growth_trajectory"),
            "churn_risk_flag":    record.get("churn_risk_flag", False),
        }

        try:
            response = self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": STRATEGY_SYSTEM_PROMPT},
                    {"role": "user",   "content": json.dumps(payload)},
                ],
                temperature=0.3,
                max_tokens=800,
                response_format={"type": "json_object"},
            )

            latency  = round(time.time() - t0, 2)
            raw_text = response.choices[0].message.content.strip()
            usage    = response.usage

            logger.info(
                f"strategy LLM [{record.get('company')}]: {latency}s | "
                f"tokens in={usage.prompt_tokens} out={usage.completion_tokens}"
            )

            parsed = self._parse_llm_response(raw_text)
            if parsed is None:
                logger.warning(f"strategy LLM: unparseable response for {record.get('company')} — using heuristic")
            return parsed

        except Exception as e:
            logger.warning(f"strategy LLM: failed for {record.get('company')} ({e}) — using heuristic")
            return None

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

        required = {"hook", "angle", "email", "personas", "competitive"}
        if not required.issubset(data.keys()):
            logger.warning(f"strategy LLM: missing fields {required - data.keys()}")
            return None

        personas = data.get("personas", {})
        if not all(p in personas for p in ("vp_sales", "ceo", "cto")):
            logger.warning("strategy LLM: incomplete persona block — using heuristic")
            return None

        return data

    def _generate_hook(
        self,
        company: str,
        signals: List[str],
        tech: List[str],
        funding: str,
        employees: int,
    ) -> str:
        parts = []

        if "growth_funding" in signals and funding:
            parts.append(f"recently closed {funding}")
        if "hiring_aggressively" in signals and employees:
            parts.append(f"scaling headcount aggressively (now {employees} employees)")
        if "mid_market_growth" in signals:
            parts.append("expanding into mid-market")
        if tech:
            infra = [t for t in tech if t in ("AWS", "GCP", "Azure", "Kubernetes", "Snowflake")]
            if infra:
                parts.append(f"running infra on {', '.join(infra[:2])}")
        if "enterprise_scale" in signals:
            parts.append("operating at enterprise scale")
        if "churn_risk" in signals:
            parts.append("showing vendor consolidation signals")

        if not parts:
            return f"{company} is showing early signals of growth"
        if len(parts) == 1:
            return f"{company} has {parts[0]}"
        return f"{company} has {parts[0]} and is {parts[1]}" + (
            f", with {parts[2]}" if len(parts) > 2 else ""
        )

    def _generate_angle(
        self,
        signals: List[str],
        insight: str,
        tech: List[str],
        industry: str,
    ) -> str:
        if "growth_funding" in signals and "hiring_aggressively" in signals:
            return (
                "help scale outbound efficiency before headcount growth outpaces pipeline — "
                "funded teams that hire fast often see SDR productivity drop without better tooling"
            )
        if "enterprise_scale" in signals and "churn_risk" in signals:
            tech_debt = [t for t in tech if t in ("Salesforce", "HubSpot", "Oracle")]
            if tech_debt:
                return (
                    f"position as a consolidation play — they're running {tech_debt[0]} "
                    f"and showing vendor fatigue signals, making them receptive to stack simplification"
                )
            return "consolidate their GTM stack — late-stage companies optimise cost per acquisition"
        if "growth_funding" in signals and "mid_market_growth" in signals:
            return (
                "convert funding into pipeline velocity — Series B/C companies have budget "
                "but need to prove GTM efficiency to justify their next round"
            )
        if "early_funding" in signals:
            cloud = [t for t in tech if t in ("AWS", "GCP", "Azure")]
            if cloud:
                return (
                    f"deliver enterprise-grade targeting on a startup budget — "
                    f"they're already on {cloud[0]}, so integration is a sprint not a quarter"
                )
            return "prove fast time-to-value — early-stage teams can't afford long implementation cycles"
        if "late_stage" in signals:
            return (
                "defend win rate without adding headcount — late-stage companies "
                "prioritise efficiency and vendor ROI over new tool adoption"
            )
        return insight or "lead with outcome-based ROI and comparable case studies"

    def _generate_email(
        self,
        company: str,
        hook: str,
        angle: str,
        signals: List[str],
        tech: List[str],
    ) -> str:
        opener = hook[0].lower() + hook[1:] if hook else f"{company} is growing"
        crm = [t for t in tech if t in ("Salesforce", "HubSpot")]
        tech_note = f"\n\nWe integrate directly with {crm[0]}, so there's no rip-and-replace." if crm else ""

        return (
            f"Hi,\n\n"
            f"Noticed that {opener}.\n\n"
            f"For teams in this stage, we typically see the biggest wins when we {angle}.\n"
            f"{tech_note}\n"
            f"We've helped similar companies shorten their sales cycle by 30-40%. "
            f"Open to a 15-min call?\n\n"
            f"Best"
        )

    def _generate_personas(
        self, company: str, signals: List[str], insight: str, industry: str, tech: List[str]
    ) -> Dict[str, Dict[str, str]]:
        return {
            "vp_sales": self._persona_vp_sales(company, signals, tech),
            "ceo":      self._persona_ceo(company, signals, insight),
            "cto":      self._persona_cto(company, signals, industry, tech),
        }

    def _persona_vp_sales(self, company: str, signals: List[str], tech: List[str]) -> Dict[str, str]:
        crm = next((t for t in tech if t in ("Salesforce", "HubSpot")), None)

        if "growth_funding" in signals and "hiring_aggressively" in signals:
            pain  = "scaling outbound without burning reps out as headcount grows"
            value = "automated signal-based prospecting that fills pipeline while your team closes"
            hook  = f"Hi — saw {company} is hiring SDRs post-funding. Most VP Sales at this stage say {pain} is the #1 bottleneck."
        elif "churn_risk" in signals:
            pain  = "justifying the current GTM stack cost to the CFO"
            value = "a leaner, higher-signal alternative that consolidates 2-3 tools into one"
            hook  = f"Hi — {company} is at a stage where GTM tool ROI gets scrutinised. We help VP Sales make that case easily."
        else:
            pain  = "hitting quota with a lean team"
            value = "smarter account prioritisation so reps focus only on deals likely to close"
            hook  = f"Hi — {company}'s growth trajectory caught our eye. Reps at companies like yours close 40% more when targeting is signal-driven."

        return {
            "persona":    "VP of Sales",
            "pain_point": pain,
            "value_prop": value,
            "hook":       hook + (f" We plug directly into {crm}." if crm else ""),
            "cta":        "Worth a quick look at how we've helped similar teams?",
        }

    def _persona_ceo(self, company: str, signals: List[str], insight: str) -> Dict[str, str]:
        if "growth_funding" in signals:
            pain  = "converting funding into predictable revenue before the next raise"
            value = "a GTM intelligence layer that ensures every outbound dollar hits the right account"
            hook  = f"Hi — {company}'s {insight or 'recent funding'} is a strong signal. CEOs at this stage need pipeline certainty, not just activity."
        elif "late_stage" in signals or "enterprise_scale" in signals:
            pain  = "defending market share while cutting cost per acquisition"
            value = "competitive intelligence + ICP refinement that improves win rate without adding headcount"
            hook  = f"Hi — at {company}'s scale, GTM efficiency is a board-level metric. We've helped similar companies cut CAC by 25%."
        else:
            pain  = "getting to repeatable revenue as efficiently as possible"
            value = "an AI-powered GTM engine that lets a small team punch above its weight"
            hook  = f"Hi — {company} is at the stage where GTM foundations determine whether you hit Series A. We help founders build that foundation fast."

        return {
            "persona":    "CEO",
            "pain_point": pain,
            "value_prop": value,
            "hook":       hook,
            "cta":        "Happy to share a 2-slide breakdown — worth 10 minutes?",
        }

    def _persona_cto(self, company: str, signals: List[str], industry: str, tech: List[str]) -> Dict[str, str]:
        cloud      = next((t for t in tech if t in ("AWS", "GCP", "Azure")), "your cloud")
        data_tools = [t for t in tech if t in ("Snowflake", "dbt", "Kafka", "PostgreSQL")]

        if "enterprise_scale" in signals:
            pain  = "keeping the GTM data stack clean and compliant at scale"
            value = f"a compliant, API-first enrichment layer that runs natively on {cloud}"
            hook  = (
                f"Hi — at {company}'s scale, GTM data debt compounds fast. "
                f"Our pipeline integrates with {cloud}"
                + (f" and {data_tools[0]}" if data_tools else "")
                + " in a single sprint."
            )
        elif "growth_funding" in signals:
            pain  = "building GTM tooling without pulling engineering off core product"
            value = f"a plug-and-play intelligence API — ships in days, not quarters, runs on {cloud}"
            hook  = f"Hi — {company} is scaling fast. CTOs at this stage tell us the hidden cost is GTM tooling requests from the sales team. We fix that without touching your roadmap."
        else:
            pain  = "maintaining data quality across fragmented sales tools"
            value = "a single enrichment + scoring layer that keeps your CRM clean automatically"
            hook  = f"Hi — {company}'s tech stack is a good fit for our API. Five-minute integration, no data pipeline changes."

        return {
            "persona":    "CTO",
            "pain_point": pain,
            "value_prop": value,
            "hook":       hook,
            "cta":        "Want me to send over our API docs? Fastest 5-minute read this week.",
        }

    def _generate_competitive(
        self, company: str, signals: List[str], industry: str, tech: List[str]
    ) -> Dict[str, str]:
        return {
            "likely_stack":         self._infer_competitors(industry, signals, tech),
            "positioning_strategy": self._infer_positioning(signals, tech),
            "differentiation":      (
                "Unlike point solutions requiring months of integration, "
                "our platform delivers enriched, scored accounts out of the box — "
                "with a feedback loop that improves targeting with every run."
            ),
        }

    def _infer_competitors(self, industry: str, signals: List[str], tech: List[str]) -> str:
        base = "Apollo, ZoomInfo, Clearbit"
        crm  = [t for t in tech if t in ("Salesforce", "HubSpot")]

        if industry == "fintech":
            return f"{base}, Bombora (finance-specific intent data)" + (f", {crm[0]} native tools" if crm else "")
        if industry in ("health", "healthtech"):
            return f"{base}, Definitive Healthcare"
        if "enterprise_scale" in signals:
            return f"{base}, Salesforce Data Cloud, 6sense" + (f" (incumbent: {crm[0]})" if crm else "")
        if "early_funding" in signals:
            return "Apollo, Clay, Hunter.io"
        return base + (f" (running on {crm[0]})" if crm else "")

    def _infer_positioning(self, signals: List[str], tech: List[str]) -> str:
        crm = next((t for t in tech if t in ("Salesforce", "HubSpot")), None)

        if "growth_funding" in signals and "hiring_aggressively" in signals:
            return (
                "Position as the intelligence layer that converts headcount growth into pipeline growth. "
                "Lead with speed-to-value and automated signal detection. "
                + (f"Emphasise {crm} integration as zero-friction." if crm else "")
            )
        if "late_stage" in signals or "churn_risk" in signals:
            return (
                "Position as a consolidation play — replace 2-3 point tools with one enrichment + scoring platform. "
                "Lead with cost reduction, data quality, and CFO-friendly ROI narrative."
            )
        if "early_funding" in signals:
            return (
                "Position as the GTM foundation for early-stage teams. "
                "Lead with ease of setup and founder-friendly pricing."
            )
        return (
            "Position on outcome-based ROI. "
            "Lead with case studies from comparable companies at the same growth stage."
        )