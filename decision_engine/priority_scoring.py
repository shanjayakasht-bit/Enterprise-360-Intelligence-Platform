"""Transparent, domain-specific priority scoring for every decision type.

Every formula follows the same conceptual shape:

    Priority Score = Risk Component + Business Impact Component
                    + Urgency Component + Strategic Importance Component

...but the WEIGHTS differ by business domain, because the four domains
don't share the same risk/impact/urgency balance (a collections decision is
almost entirely about dollar exposure and how overdue it already is; a
retention decision leans more on the risk signal itself). Every component
is normalized to [0, 100] BEFORE weighting (see decision_engine/common.py's
normalize()), so the weighted sum is always in [0, 100] directly -- no
further rescaling needed. Weights are declared once, per domain, below, and
every one of them sums to exactly 1.0 (100%).

severity is then derived from priority_score via
decision_engine.common.severity_from_score() (0-39 LOW, 40-59 MEDIUM,
60-79 HIGH, 80-100 CRITICAL).
"""

WEIGHTS = {
    # Retention decisions lean on the risk signal (whatever its actual
    # reliability -- see confidence_score) since "is this customer
    # unhealthy" is the central question; impact and strategic tier follow.
    "CUSTOMER_RETENTION": {"risk": 0.40, "impact": 0.30, "urgency": 0.15, "strategic": 0.15},

    # Delivery risk decisions weight risk and dollar exposure almost evenly,
    # with urgency (time truly remaining) mattering more here than for
    # retention -- a project doesn't have a "renewal date" cushion.
    "PROJECT_DELIVERY": {"risk": 0.35, "impact": 0.30, "urgency": 0.20, "strategic": 0.15},

    # Collections is fundamentally about how much money is at stake and how
    # overdue it already is -- impact and urgency together outweigh the
    # (real, Phase-4-validated) risk signal here, and strategic tier matters
    # least of the four domains (a small overdue invoice is still an
    # overdue invoice, regardless of segment).
    "PAYMENT_COLLECTION": {"risk": 0.35, "impact": 0.35, "urgency": 0.20, "strategic": 0.10},

    # Revenue opportunity/downside signals are inherently strategic and
    # dollar-driven; "risk" here means the strength/magnitude of the signal
    # itself (how big a swing, how strong the association lift, etc.), not
    # a classifier probability.
    "REVENUE_OPPORTUNITY": {"risk": 0.35, "impact": 0.35, "urgency": 0.15, "strategic": 0.15},

    # Anomaly decisions lead with how statistically extreme the anomaly is;
    # impact reflects what's actually exposed (that customer's ARR or that
    # project's budget); urgency defaults moderate (an anomaly was just
    # detected, not scheduled) unless the domain module can derive better.
    "BUSINESS_ANOMALY": {"risk": 0.40, "impact": 0.30, "urgency": 0.15, "strategic": 0.15},
}

for _decision_type, _weights in WEIGHTS.items():
    _total = round(sum(_weights.values()), 6)
    assert _total == 1.0, f"{_decision_type} weights sum to {_total}, not 1.0"


def compute_priority(decision_type, risk, impact, urgency, strategic):
    """risk/impact/urgency/strategic must already be normalized to [0, 100].
    Returns priority_score in [0, 100]."""
    w = WEIGHTS[decision_type]
    score = w["risk"] * risk + w["impact"] * impact + w["urgency"] * urgency + w["strategic"] * strategic
    return round(max(0.0, min(100.0, score)), 2)
