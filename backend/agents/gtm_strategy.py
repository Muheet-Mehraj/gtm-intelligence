import json
import logging
import os
import time
from typing import List, Dict, Any

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.strategy")

PERSONAS = ["vp_sales", "ceo", "cto"]

GTM_SYSTEM_PROMPT = """You are a B2B GTM strategist. Generate highly specific, signal-driven outreach strategy for a target company.

You will receive a company profile with signals, funding, tech stack, and employee count.
Return ONLY a JSON object with this exact schema:

{
  "hook": "<one punchy sentence about what makes this company a target right now — use their real signals, funding round, headcount>",
  "angle": "<one sentence on the core GTM angle — why your product wins HERE, not generic>",
  "email": "<a 4-6 line cold email. Start with 'Hi [Name],' then a specific observation about the company, then value prop, then soft CTA. Use the company's actual name with correct capitalisation.>",
  "personas": {
    "vp_sales": {
      "persona": "VP of Sales",
      "pain_point": "<specific pain given their signals and stage>",
      "value_prop": "<specific value given their tech stack and signals>",
      "hook": "<personalised one-liner opening for VP Sales outreach>",
      "cta": "<specific call to action>"
    },
    "ceo": {
      "persona": "CEO / Founder",
      "pain_point": "<specific pain given their funding stage and growth trajectory>",
      "value_prop": "<specific value>",
      "hook": "<personalised one-liner opening for CEO outreach>",
      "cta": "<specific call to action>"
    },
    "cto": {
      "persona": "CTO / Head of Engineering",
      "pain_point": "<specific pain given their tech stack>",
      "value_prop": "<specific value referencing their actual cloud/tools>",
      "hook": "<personalised one-liner opening for CTO outreach>",
      "cta": "<specific call to action>"
    }
  },
  "competitive": {
    "likely_stack": "<comma-separated list of tools they're probably using based on their tech stack and signals>",
    "positioning_strategy": "<one sentence on how to position against their current stack>",
    "differentiation": "<one sentence on your key differentiator for this specific company>"
  }
}

Rules:
- Use the company's EXACT name with correct capitalisation everywhere
- Never use generic phrases like "limited signal" or "early exploratory opportunity" in customer-facing content
- Every field must be specific to THIS company — no copy-paste across companies
- Email must feel handwritten, not templated
- Return ONLY the JSON object, no markdown, no preamble"""


class GTMStrategyAgent:
    """
    Converts enriched results into insight-driven GTM messaging.

    Primary path: Groq LLM per company (llama-3.1-70b-versatile) — specific, non-templated output
    Fallback: signal-based template engine if Groq is unavailable or rate-limited
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
                logger.info("gtm_strategy: Groq client initialised")
            else:
                logger.warning("gtm_strategy: GROQ_API_KEY not set — template fallback active")
        except ImportError:
            logger.warning("gtm_strategy: groq package not installed — template fallback active")

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("strategy started")

        try:
            enriched = state.enriched_results or []

            hooks, angles, emails, personas, competitive = [], [], [], [], []
            llm_count = 0
            template_count = 0
            total_latency = 0.0

            for record in enriched:
                company = record.get("company")
                if not company:
                    continue

                # Try LLM first, fall back to templates per-company
                if self._groq_client:
                    result, used_llm, latency = self._llm_strategy(record)
                    total_latency += latency
                    if used_llm:
                        llm_count += 1
                    else:
                        template_count += 1
                        result = self._template_strategy(record)
                else:
                    result = self._template_strategy(record)
                    template_count += 1

                hooks.append({"company": company, "hook": result["hook"]})
                angles.append({"company": company, "angle": result["angle"]})
                emails.append({"company": company, "email": result["email"]})
                personas.append({"company": company, "personas": result["personas"]})
                competitive.append({"company": company, "competitive": result["competitive"]})

            state.gtm_strategy = {
                "hooks":                   hooks,
                "angles":                  angles,
                "email_snippets":          emails,
                "persona_targeting":       personas,
                "competitive_intelligence":competitive,
            }

            # Observability
            state.memory.setdefault("metrics", {})["gtm_strategy"] = {
                "llm_companies":      llm_count,
                "template_companies": template_count,
                "total_latency_s":    round(total_latency, 2),
                "source": "groq/llama-3.1-70b-versatile" if llm_count > 0 else "template",
            }

            source_note = (
                f"groq LLM ({llm_count}) + template fallback ({template_count})"
                if template_count > 0 and llm_count > 0
                else f"groq LLM ({llm_count})" if llm_count > 0
                else f"template ({template_count})"
            )

            state.add_trace(
                f"generated GTM strategy for {len(hooks)} companies "
                f"via {source_note} in {total_latency:.2f}s"
            )
            state.add_log("gtm strategy created")
            return state

        except Exception as e:
            logger.error(f"strategy error: {str(e)}")
            state.errors.append(str(e))
            state.gtm_strategy = {"hooks": [], "angles": [], "email_snippets": []}
            return state

    # ── LLM strategy generation ───────────────────────────────────────

    def _llm_strategy(self, record: Dict[str, Any]) -> tuple[Dict, bool, float]:
        """
        Returns (result_dict, used_llm: bool, latency: float).
        Falls back to template silently on any Groq error.
        """
        t0 = time.time()
        company   = record.get("company", "")
        signals   = record.get("signals", [])
        funding   = record.get("funding", "")
        employees = record.get("employees", 0)
        tech      = record.get("tech_stack", [])
        industry  = record.get("industry", "")
        insight   = record.get("insight", "")
        trajectory = record.get("growth_trajectory", "")
        intent    = record.get("apollo_intent_score", 0)
        buying    = record.get("buying_signal_strength", "low")

        user_message = f"""Generate GTM strategy for this company:

Company: {company}
Industry: {industry}
Employees: {employees}
Funding: {funding}
Growth trajectory: {trajectory}
Tech stack: {', '.join(tech)}
Signals: {', '.join(signals)}
Insight: {insight}
Apollo intent score: {intent:.2f}
Buying signal strength: {buying}

Return the JSON strategy object."""

        try:
            response = self._groq_client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[
                    {"role": "system", "content": GTM_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                temperature=0.4,   # slight creativity for better copy
                max_tokens=800,
            )

            latency  = round(time.time() - t0, 2)
            raw_text = response.choices[0].message.content.strip()

            parsed = self._parse_llm_response(raw_text)
            if parsed is None:
                logger.warning(f"gtm_strategy: unparseable response for {company} — using template")
                return {}, False, latency

            # Ensure all required keys exist
            parsed = self._normalise_llm_result(parsed, record)

            logger.info(f"gtm_strategy LLM: {company} in {latency}s")
            return parsed, True, latency

        except Exception as e:
            latency = round(time.time() - t0, 2)
            logger.warning(f"gtm_strategy: Groq failed for {company} ({e}) — using template")
            return {}, False, latency

    def _parse_llm_response(self, text: str) -> Dict | None:
        import re
        text = re.sub(r"```json|```", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    return None
            return None

    def _normalise_llm_result(self, parsed: Dict, record: Dict) -> Dict:
        """Ensure all required keys exist, fill from template if any are missing."""
        company = record.get("company", "")
        template = self._template_strategy(record)

        return {
            "hook":       parsed.get("hook")       or template["hook"],
            "angle":      parsed.get("angle")      or template["angle"],
            "email":      parsed.get("email")      or template["email"],
            "personas":   parsed.get("personas")   or template["personas"],
            "competitive":parsed.get("competitive")or template["competitive"],
        }

    # ── Template fallback ─────────────────────────────────────────────

    def _template_strategy(self, record: Dict[str, Any]) -> Dict:
        company   = record.get("company", "")
        signals   = record.get("signals", [])
        insight   = record.get("insight", "")
        industry  = record.get("industry", "")
        tech      = record.get("tech_stack", [])
        funding   = record.get("funding", "")
        employees = record.get("employees", 0)

        hook  = self._generate_hook(company, signals, tech, funding, employees)
        angle = self._generate_angle(signals, insight, tech, industry)
        email = self._generate_email(company, hook, angle, signals, tech)

        return {
            "hook":  hook,
            "angle": angle,
            "email": email,
            "personas":    self._generate_personas(company, signals, insight, industry, tech),
            "competitive": self._generate_competitive(company, signals, industry, tech),
        }

    # ── Template helpers ──────────────────────────────────────────────

    def _generate_hook(self, company, signals, tech, funding, employees) -> str:
        parts = []
        if "growth_funding" in signals and funding:
            parts.append(f"recently closed {funding}")
        if "hiring_aggressively" in signals and employees:
            parts.append(f"scaling headcount to {employees} employees")
        if "mid_market_growth" in signals:
            parts.append("expanding into mid-market")
        infra = [t for t in tech if t in ("AWS", "GCP", "Azure", "Kubernetes", "Snowflake")]
        if infra:
            parts.append(f"running infra on {', '.join(infra[:2])}")
        if "enterprise_scale" in signals:
            parts.append("operating at enterprise scale")
        if "churn_risk" in signals:
            parts.append("showing vendor consolidation signals")

        if not parts:
            return f"{company} is an early-stage opportunity worth tracking"
        if len(parts) == 1:
            return f"{company} has {parts[0]}"
        return f"{company} has {parts[0]} and is {parts[1]}" + (
            f", with {parts[2]}" if len(parts) > 2 else ""
        )

    def _generate_angle(self, signals, insight, tech, industry) -> str:
        if "growth_funding" in signals and "hiring_aggressively" in signals:
            return (
                "help scale outbound efficiency before headcount growth outpaces pipeline — "
                "funded teams that hire fast often see SDR productivity drop without better tooling"
            )
        if "enterprise_scale" in signals and "churn_risk" in signals:
            tech_debt = [t for t in tech if t in ("Salesforce", "HubSpot", "Oracle")]
            if tech_debt:
                return (
                    f"position as a consolidation play — running {tech_debt[0]} "
                    f"with vendor fatigue signals makes them receptive to stack simplification"
                )
            return "consolidate their GTM stack — late-stage companies optimise cost per acquisition"
        if "growth_funding" in signals and "mid_market_growth" in signals:
            return (
                "convert funding into pipeline velocity — Series B/C companies have budget "
                "but need to prove GTM efficiency to justify their next round"
            )
        if "early_funding" in signals or "early_stage_team" in signals:
            cloud = [t for t in tech if t in ("AWS", "GCP", "Azure")]
            if cloud:
                return (
                    f"deliver enterprise-grade targeting on a startup budget — "
                    f"already on {cloud[0]}, so integration is a sprint not a quarter"
                )
            return "prove fast time-to-value — early-stage teams need quick wins, not long implementations"
        if "late_stage" in signals:
            return (
                "defend win rate without adding headcount — late-stage companies "
                "prioritise efficiency and vendor ROI over new tool adoption"
            )
        return "lead with outcome-based ROI and comparable case studies from similar-stage companies"

    def _generate_email(self, company, hook, angle, signals, tech) -> str:
        # Build opener from hook without creating "I noticed noticed that..."
        # Hook is like "ScaleAI has recently closed Series E and is scaling..."
        # We want: "I noticed ScaleAI recently closed Series E and is scaling..."
        if hook.startswith(company):
            rest = hook[len(company):].strip()
            # drop leading "has" to make it past tense naturally
            if rest.startswith("has "):
                rest = rest[4:]
            opener_clause = f"{company} {rest}"
        else:
            opener_clause = hook

        tech_note = ""
        crm = [t for t in tech if t in ("Salesforce", "HubSpot")]
        if crm:
            tech_note = f"\n\nWe integrate directly with {crm[0]}, so there's no rip-and-replace."

        return (
            f"Hi,\n\n"
            f"I noticed {opener_clause}.\n\n"
            f"For teams at this stage, the biggest wins usually come when you {angle}.\n"
            f"{tech_note}\n"
            f"We've helped similar companies shorten their sales cycle by 30–40%. "
            f"Worth a 15-min call?\n\n"
            f"Best"
        )

    def _generate_personas(self, company, signals, insight, industry, tech) -> Dict:
        return {
            "vp_sales": self._persona_vp_sales(company, signals, tech),
            "ceo":      self._persona_ceo(company, signals, insight),
            "cto":      self._persona_cto(company, signals, industry, tech),
        }

    def _persona_vp_sales(self, company, signals, tech) -> Dict:
        crm = next((t for t in tech if t in ("Salesforce", "HubSpot")), None)
        if "growth_funding" in signals and "hiring_aggressively" in signals:
            pain  = "scaling outbound without burning reps out as headcount grows"
            value = "automated signal-based prospecting that fills pipeline while your team closes"
            hook  = f"Hi — saw {company} is hiring aggressively post-funding. Most VP Sales at this stage say {pain} is the #1 bottleneck."
        elif "churn_risk" in signals:
            pain  = "justifying the current GTM stack cost to the CFO"
            value = "a leaner, higher-signal alternative that consolidates 2–3 tools into one"
            hook  = f"Hi — {company} is at a stage where GTM tool ROI gets scrutinised. We help VP Sales make that case easily."
        else:
            pain  = "hitting quota with a lean team"
            value = "smarter account prioritisation so reps focus only on deals likely to close"
            hook  = f"Hi — {company}'s growth trajectory caught our eye. Reps at companies like yours close 40% more when targeting is signal-driven."
        return {
            "persona": "VP of Sales", "pain_point": pain, "value_prop": value,
            "hook": hook + (f" We plug directly into {crm}." if crm else ""),
            "cta": "Worth a quick look at how we've helped similar teams?",
        }

    def _persona_ceo(self, company, signals, insight) -> Dict:
        if "growth_funding" in signals:
            pain  = "converting funding into predictable revenue before the next raise"
            value = "a GTM intelligence layer that ensures every outbound dollar hits the right account"
            hook  = f"Hi — {company} just raised and now needs to prove pipeline efficiency. CEOs at this stage need certainty, not just activity."
        elif "late_stage" in signals or "enterprise_scale" in signals:
            pain  = "defending market share while cutting cost per acquisition"
            value = "competitive intelligence + ICP refinement that improves win rate without adding headcount"
            hook  = f"Hi — at {company}'s scale, GTM efficiency is a board-level metric. We've helped similar companies cut CAC by 25%."
        else:
            pain  = "getting to repeatable revenue as efficiently as possible"
            value = "an AI-powered GTM engine that lets a small team punch above its weight"
            hook  = f"Hi — {company} is at the stage where GTM foundations determine the next round. We help teams build that foundation fast."
        return {
            "persona": "CEO / Founder", "pain_point": pain, "value_prop": value,
            "hook": hook, "cta": "Happy to share a 2-slide breakdown — worth 10 minutes?",
        }

    def _persona_cto(self, company, signals, industry, tech) -> Dict:
        cloud      = next((t for t in tech if t in ("AWS", "GCP", "Azure")), "your cloud")
        data_tools = [t for t in tech if t in ("Snowflake", "dbt", "Kafka", "PostgreSQL")]
        if "enterprise_scale" in signals:
            pain  = "keeping the GTM data stack clean and compliant at scale"
            value = f"a compliant, API-first enrichment layer that runs natively on {cloud}"
            hook  = f"Hi — at {company}'s scale, GTM data debt compounds fast. Our pipeline integrates with {cloud}" + (f" and {data_tools[0]}" if data_tools else "") + " in a single sprint."
        elif "growth_funding" in signals:
            pain  = "building GTM tooling without pulling engineering off core product"
            value = f"a plug-and-play intelligence API — ships in days, runs on {cloud}"
            hook  = f"Hi — {company} is scaling fast. CTOs at this stage say the hidden cost is GTM tooling requests from sales. We fix that without touching your roadmap."
        else:
            pain  = "maintaining data quality across fragmented sales tools"
            value = "a single enrichment + scoring layer that keeps your CRM clean automatically"
            hook  = f"Hi — {company}'s tech stack is a good fit for our API. Five-minute integration, no pipeline changes."
        return {
            "persona": "CTO / Head of Engineering", "pain_point": pain, "value_prop": value,
            "hook": hook, "cta": "Want me to send over our API docs? Fastest 5-minute read this week.",
        }

    def _generate_competitive(self, company, signals, industry, tech) -> Dict:
        competitors  = self._infer_competitors(industry, signals, tech)
        positioning  = self._infer_positioning(signals, tech)
        return {
            "likely_stack": competitors,
            "positioning_strategy": positioning,
            "differentiation": (
                "Unlike point solutions requiring months of integration, "
                "our platform delivers enriched, scored accounts out of the box — "
                "with a feedback loop that improves targeting with every run."
            ),
        }

    def _infer_competitors(self, industry, signals, tech) -> str:
        base = "Apollo, ZoomInfo, Clearbit"
        crm  = [t for t in tech if t in ("Salesforce", "HubSpot")]
        if industry == "fintech":
            return f"{base}, Bombora" + (f", {crm[0]} native tools" if crm else "")
        if industry in ("health", "healthtech"):
            return f"{base}, Definitive Healthcare"
        if "enterprise_scale" in signals:
            return f"{base}, Salesforce Data Cloud, 6sense" + (f" (incumbent: {crm[0]})" if crm else "")
        if "early_funding" in signals or "early_stage_team" in signals:
            return "Apollo, Clay, Hunter.io"
        return base + (f" (running on {crm[0]})" if crm else "")

    def _infer_positioning(self, signals, tech) -> str:
        crm = next((t for t in tech if t in ("Salesforce", "HubSpot")), None)
        if "growth_funding" in signals and "hiring_aggressively" in signals:
            return (
                "Position as the intelligence layer that converts headcount growth into pipeline growth. "
                "Lead with speed-to-value and automated signal detection."
                + (f" Emphasise {crm} integration as zero-friction." if crm else "")
            )
        if "late_stage" in signals or "churn_risk" in signals:
            return (
                "Position as a consolidation play — replace 2–3 point tools with one enrichment + scoring platform. "
                "Lead with cost reduction, data quality, and CFO-friendly ROI narrative."
            )
        if "early_funding" in signals or "early_stage_team" in signals:
            return (
                "Position as the GTM foundation for early-stage teams. "
                "Lead with ease of setup and founder-friendly pricing."
            )
        return (
            "Position on outcome-based ROI. "
            "Lead with case studies from comparable companies at the same growth stage."
        )