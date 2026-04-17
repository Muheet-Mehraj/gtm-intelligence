import logging
from typing import List, Dict, Any

from backend.orchestrator.state import AgentState

logger = logging.getLogger("gtm.retrieval")


class RetrievalAgent:
    """
    Fetches data based on planner output.
    Uses deterministic mock dataset.
    """

    def __call__(self, state: AgentState) -> AgentState:
        logger.info("retrieval started")

        try:
            plan = state.plan or {}
            results = self._fetch(plan)

            state.raw_results = results

            state.add_trace(f"retrieved {len(results)} records")
            state.add_log(f"raw_results: {len(state.raw_results)}")

            return state

        except Exception as e:
            logger.error(f"retrieval error: {str(e)}")
            state.errors.append(str(e))
            state.raw_results = []
            return state

    def _fetch(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        filters = plan.get("filters", {})
        industry = filters.get("industry", "AI").strip().lower()
        region = filters.get("region", "global").strip().lower()

        data = self._mock_data()
        scored_results = []

        for item in data:
            score = 0

            item_industry = item.get("industry", "").lower()
            item_region = item.get("region", "").lower()

            # --- Industry matching (flexible, unchanged logic) ---
            if industry in item_industry:
                score += 2
            elif item_industry in industry:
                score += 1

            # --- Region matching ---
            if region == "global":
                score += 1
            elif item_region == region:
                score += 2

            # --- Keyword boost ---
            keywords = filters.get("keywords", [])
            for kw in keywords:
                if kw.lower() in str(item).lower():
                    score += 1

            # --- Keep relevant results ---
            if score > 2:
                item_copy = item.copy()  # prevent mutation issues
                item_copy["retrieval_score"] = score
                scored_results.append((score, item_copy))

        # --- Fallback ---
        if not scored_results:
            logger.warning("no matches found — using fallback")
            return data[:3]

        # --- Sort by score ---
        scored_results.sort(key=lambda x: x[0], reverse=True)

        return [item for _, item in scored_results]

    def _mock_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "company": "ScaleAI",
                "industry": "AI",
                "region": "US",
                "employees": 800,
                "funding": "Series E",
            },
            {
                "company": "OpenLayer",
                "industry": "AI",
                "region": "US",
                "employees": 120,
                "funding": "Series A",
            },
            {
                "company": "DataRobot",
                "industry": "AI",
                "region": "US",
                "employees": 2000,
                "funding": "Late Stage",
            },
            {
                "company": "DeepVision",
                "industry": "AI",
                "region": "EU",
                "employees": 60,
                "funding": "Seed",
            },
            {
                "company": "FinEdge",
                "industry": "fintech",
                "region": "US",
                "employees": 300,
                "funding": "Series B",
            },
            {
                "company": "HealthSync",
                "industry": "health",
                "region": "EU",
                "employees": 150,
                "funding": "Series A",
            },
        ]