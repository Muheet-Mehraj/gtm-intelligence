"""
ICP scoring engine.
Computes a composite Ideal Customer Profile score for a company record
using signals, firmographics, and enrichment data.
"""

import logging

logger = logging.getLogger("gtm.tools.scoring")

# Signal weights — tunable per ICP definition
SIGNAL_WEIGHTS = {
    "growth_funding":       0.30,
    "mid_market_growth":    0.20,
    "hiring_aggressively":  0.15,
    "enterprise_scale":     0.10,
    "early_funding":        0.08,
    "late_stage":           0.05,
    "early_stage_team":     0.05,
    "churn_risk":           0.07,  # positive for displacement plays
}

EMPLOYEE_SCORE = {
    (0,    49):   0.10,
    (50,   199):  0.20,
    (200,  999):  0.35,
    (1000, 4999): 0.25,
    (5000, 99999):0.10,
}

FUNDING_SCORE = {
    "Seed":     0.10,
    "Series A": 0.20,
    "Series B": 0.30,
    "Series C": 0.40,
    "Series D": 0.45,
    "Series E": 0.45,
    "Series F": 0.40,
    "Series G": 0.35,
    "Late Stage": 0.30,
    "Public":   0.25,
}


def score_company(record: dict) -> float:
    """
    Returns a float [0.0, 1.0] representing ICP fit.
    Higher = stronger fit for outbound targeting.
    """
    score = 0.0

    # 1. Signal-based score (max ~0.60)
    signals = record.get("signals", [])
    for sig in signals:
        score += SIGNAL_WEIGHTS.get(sig, 0.0)

    # 2. Employee band score (max ~0.35)
    employees = record.get("employees", 0)
    for (low, high), pts in EMPLOYEE_SCORE.items():
        if low <= employees <= high:
            score += pts
            break

    # 3. Funding stage score (max ~0.45)
    funding = record.get("funding", "")
    score += FUNDING_SCORE.get(funding, 0.0)

    # 4. Apollo intent boost
    intent = record.get("apollo_intent_score", 0.0)
    score += intent * 0.10

    # 5. Explorium fit boost
    fit = record.get("explorium_fit_score", 0.0)
    score += fit * 0.05

    # 6. Penalty: churn risk without buying signal
    buying_strength = record.get("buying_signal_strength", "low")
    if record.get("churn_risk_flag") and buying_strength == "low":
        score -= 0.10

    final = round(min(max(score, 0.0), 1.0), 2)
    logger.debug(f"scored {record.get('company')}: {final}")
    return final


def rank_companies(records: list) -> list:
    """Sort records by ICP score descending. Attaches score to each record."""
    for r in records:
        r["icp_score"] = score_company(r)
    return sorted(records, key=lambda r: r["icp_score"], reverse=True)