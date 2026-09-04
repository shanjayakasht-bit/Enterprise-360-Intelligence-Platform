"""Revenue shaping and risk-scoring formulas shared by generators and validators."""

from .master_data import REGION_REVENUE_MULTIPLIER, RNG, SEGMENT_REVENUE_MULTIPLIER, seasonality_multiplier


def discount_pct(segment, deal_value, rng=RNG):
    """Larger deals and enterprise accounts negotiate steeper discounts."""
    base = {"Enterprise": 0.14, "Mid-Market": 0.08, "SMB": 0.04, "Startup": 0.03}[segment]
    size_bump = min(0.10, deal_value / 500_000 * 0.10)
    noise = rng.uniform(-0.02, 0.03)
    return round(max(0.0, min(0.35, base + size_bump + noise)), 4)


def priced_amount(base_amount, region, segment, month, rng=RNG, noise=0.08):
    """Applies regional, segment, and seasonal multipliers plus jitter to a base price."""
    multiplier = REGION_REVENUE_MULTIPLIER[region] * SEGMENT_REVENUE_MULTIPLIER[segment] * seasonality_multiplier(month)
    jitter = 1 + rng.uniform(-noise, noise)
    return round(base_amount * multiplier * jitter, 2)


CUSTOMER_RISK_WEIGHTS = {
    "usage": 0.20,
    "engagement": 0.15,
    "satisfaction": 0.20,
    "support": 0.15,
    "payment": 0.15,
    "renewal": 0.15,
}


def customer_risk_components(usage_score, engagement_score, satisfaction_score,
                              support_tickets_recent, avg_payment_delay_days, days_to_renewal):
    return {
        "usage": 100 - usage_score,
        "engagement": 100 - engagement_score,
        "satisfaction": 100 - satisfaction_score,
        "support": min(100.0, support_tickets_recent * 12),
        "payment": min(100.0, max(0.0, avg_payment_delay_days) * 4),
        "renewal": max(0.0, min(100.0, 100 - (days_to_renewal / 365 * 100))),
    }


def customer_risk_score(usage_score, engagement_score, satisfaction_score,
                         support_tickets_recent, avg_payment_delay_days, days_to_renewal):
    """Risk rises as usage/engagement/satisfaction fall, tickets and payment delays rise,
    and the renewal date approaches."""
    components = customer_risk_components(
        usage_score, engagement_score, satisfaction_score,
        support_tickets_recent, avg_payment_delay_days, days_to_renewal,
    )
    score = sum(components[k] * CUSTOMER_RISK_WEIGHTS[k] for k in CUSTOMER_RISK_WEIGHTS)
    score = round(max(0.0, min(100.0, score)), 1)
    return score, risk_category(score)


def risk_category(score):
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


PROJECT_RISK_WEIGHTS = {
    "completion": 0.30,
    "deadline": 0.25,
    "budget": 0.20,
    "cost_overrun": 0.25,
}


def project_risk_components(completion_pct, days_to_deadline, budget_utilization_pct, cost_overrun_pct):
    return {
        "completion": 100 - completion_pct,
        "deadline": 100.0 if days_to_deadline <= 0 else max(0.0, 100 - (min(days_to_deadline, 180) / 180 * 100)),
        "budget": min(100.0, max(0.0, budget_utilization_pct - 50) * 2),
        "cost_overrun": min(100.0, max(0.0, cost_overrun_pct) * 5),
    }


def project_risk_score(completion_pct, days_to_deadline, budget_utilization_pct, cost_overrun_pct):
    """Risk rises as completion lags, the deadline nears, and budget/cost utilization climbs."""
    components = project_risk_components(completion_pct, days_to_deadline, budget_utilization_pct, cost_overrun_pct)
    score = sum(components[k] * PROJECT_RISK_WEIGHTS[k] for k in PROJECT_RISK_WEIGHTS)
    score = round(max(0.0, min(100.0, score)), 1)
    return score, risk_category(score)
