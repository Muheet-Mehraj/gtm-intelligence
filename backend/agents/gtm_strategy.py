import logging
from typing import List, Dict, Any

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.strategy")

PERSONAS = ["vp_sales", "ceo", "cto"]


class GTMStrategyAgent:
    """
    Converts enriched results into GTM messaging.
    Produces hooks, angles, email snippets, multi-persona targeting,
    and competitive positioning — fulfilling assessment sections 10B, 10C, 10D.
    """

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("strategy started")

        try:
            enriched = state.enriched_results or []

            hooks: List[Dict[str, str]] = []
            angles: List[Dict[str, str]] = []
            emails: List[Dict[str, str]] = []
            personas: List[Dict[str, Any]] = []
            competitive: List[Dict[str, str]] = []

            for record in enriched:
                company = record.get("company")
                signals = record.get("signals", [])
                insight = record.get("insight", "")
                industry = record.get("industry", "")

                if not company:
                    continue

                hook = self._generate_hook(company, signals)
                angle = self._generate_angle(signals, insight)
                email = self._generate_email(company, hook, angle)

                hooks.append({"company": company, "hook": hook})
                angles.append({"company": company, "angle": angle})
                emails.append({"company": company, "email": email})

                # Multi-persona targeting (assessment requirement 10C)
                persona_block = self._generate_personas(company, signals, insight, industry)
                personas.append({"company": company, "personas": persona_block})

                # Competitive intelligence (assessment requirement 10D)
                comp_block = self._generate_competitive(company, signals, industry)
                competitive.append({"company": company, "competitive": comp_block})

            state.gtm_strategy = {
                "hooks": hooks,
                "angles": angles,
                "email_snippets": emails,
                "persona_targeting": personas,
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

    # ── Core hook / angle / email ─────────────────────────────────────

    def _generate_hook(self, company: str, signals: List[str]) -> str:
        if "growth_funding" in signals:
            return f"{company} is scaling rapidly after recent funding"
        if "mid_market_growth" in signals:
            return f"{company} is expanding operations and hiring aggressively"
        if "early_funding" in signals:
            return f"{company} recently raised early funding and is evaluating tools"
        if "late_stage" in signals:
            return f"{company} is optimizing its stack for efficiency at scale"
        return f"{company} is showing early signals of growth"

    def _generate_angle(self, signals: List[str], insight: str) -> str:
        if "growth_funding" in signals:
            return "focus on scaling outbound efficiency and pipeline velocity"
        if "early_funding" in signals:
            return "highlight fast time-to-value and low implementation overhead"
        if "late_stage" in signals:
            return "position as a consolidation-friendly alternative to existing tools"
        if insight:
            return insight
        return "general value-based outreach"

    def _generate_email(self, company: str, hook: str, angle: str) -> str:
        return (
            f"Hi,\n\n"
            f"Noticed that {hook.lower()}.\n\n"
            f"For teams in this stage, we typically see the biggest wins by helping to "
            f"{angle}.\n\n"
            f"We've helped similar companies hit their goals faster. Open to a 15-min call?\n\n"
            f"Best"
        )

    # ── Multi-persona targeting (10C) ─────────────────────────────────

    def _generate_personas(
        self,
        company: str,
        signals: List[str],
        insight: str,
        industry: str,
    ) -> Dict[str, Dict[str, str]]:
        return {
            "vp_sales": self._persona_vp_sales(company, signals),
            "ceo": self._persona_ceo(company, signals, insight),
            "cto": self._persona_cto(company, signals, industry),
        }

    def _persona_vp_sales(self, company: str, signals: List[str]) -> Dict[str, str]:
        if "growth_funding" in signals or "mid_market_growth" in signals:
            pain = "scaling outbound without burning your reps out"
            value = "automated signal-based prospecting that fills pipeline while your team closes"
        elif "early_funding" in signals:
            pain = "building a repeatable sales motion from scratch"
            value = "a lightweight GTM layer that gives you enterprise-grade targeting on a startup budget"
        else:
            pain = "hitting quota with a lean team"
            value = "smarter account prioritization so your reps focus only on deals likely to close"

        return {
            "persona": "VP of Sales",
            "pain_point": pain,
            "value_prop": value,
            "hook": f"Hi — saw {company} is hiring SDRs. Most VP Sales I talk to at this stage say {pain} is the #1 bottleneck. We fix that.",
            "cta": "Would a quick look at how we've helped similar teams make sense?",
        }

    def _persona_ceo(self, company: str, signals: List[str], insight: str) -> Dict[str, str]:
        if "growth_funding" in signals:
            pain = "converting funding into predictable revenue growth"
            value = "a GTM intelligence layer that ensures every outbound dollar targets the right account"
        elif "late_stage" in signals:
            pain = "defending market share while optimizing cost per acquisition"
            value = "competitive intelligence and ICP refinement that improves win rate without adding headcount"
        else:
            pain = "getting to repeatable revenue as efficiently as possible"
            value = "an AI-powered GTM engine that lets a small team punch above its weight"

        return {
            "persona": "CEO",
            "pain_point": pain,
            "value_prop": value,
            "hook": f"Hi — {company}'s trajectory caught our eye. For CEOs focused on {pain}, we typically cut time-to-first-deal by 40%.",
            "cta": "Happy to share a 2-slide breakdown of how — worth 10 minutes?",
        }

    def _persona_cto(self, company: str, signals: List[str], industry: str) -> Dict[str, str]:
        if "enterprise_scale" in signals:
            pain = "keeping the GTM data stack clean at scale"
            value = "a compliant, API-first enrichment layer that integrates with your existing infra in days"
        elif "early_funding" in signals or "growth_funding" in signals:
            pain = "building GTM tooling without pulling engineering off product"
            value = "a plug-and-play intelligence API that ships in a sprint, not a quarter"
        else:
            pain = "maintaining data quality across fragmented sales tools"
            value = "a single enrichment and scoring layer that keeps your CRM clean automatically"

        return {
            "persona": "CTO",
            "pain_point": pain,
            "value_prop": value,
            "hook": f"Hi — noticed {company} is scaling its tech stack. CTOs at {industry} companies often tell us {pain} is an underrated drag.",
            "cta": "Our API docs might be the fastest 5-minute read you have this week. Want me to send them over?",
        }

    # ── Competitive intelligence (10D) ───────────────────────────────

    def _generate_competitive(
        self,
        company: str,
        signals: List[str],
        industry: str,
    ) -> Dict[str, str]:
        likely_competitors = self._infer_competitors(industry, signals)
        positioning = self._infer_positioning(signals)

        return {
            "likely_stack": likely_competitors,
            "positioning_strategy": positioning,
            "differentiation": (
                "Unlike point solutions that require months of integration, "
                "our platform delivers enriched, scored accounts out of the box — "
                "with a feedback loop that improves targeting with every run."
            ),
        }

    def _infer_competitors(self, industry: str, signals: List[str]) -> str:
        base = "Apollo, ZoomInfo, Clearbit"
        if industry == "fintech":
            return f"{base}, Bombora (finance-specific intent data)"
        if industry == "health":
            return f"{base}, Definitive Healthcare"
        if "enterprise_scale" in signals:
            return f"{base}, Salesforce Data Cloud, 6sense"
        if "early_funding" in signals:
            return "Apollo, Clay, Hunter.io"
        return base

    def _infer_positioning(self, signals: List[str]) -> str:
        if "growth_funding" in signals:
            return (
                "Position as the intelligence layer that helps funded teams convert capital into pipeline fast. "
                "Lead with speed-to-value and automated signal detection."
            )
        if "late_stage" in signals:
            return (
                "Position as a consolidation play — replace 2-3 point tools with one enrichment + scoring platform. "
                "Lead with cost reduction and data quality."
            )
        if "early_funding" in signals:
            return (
                "Position as the GTM foundation for early-stage teams. "
                "Lead with ease of setup and founder-friendly pricing."
            )
        return (
            "Position on outcome-based ROI. "
            "Lead with case studies from comparable companies in the same growth stage."
        )