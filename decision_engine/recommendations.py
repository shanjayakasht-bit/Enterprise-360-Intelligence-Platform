"""Deterministic, rule-based recommendation mapping. No LLM anywhere in this
module -- every recommendation is a fixed string chosen by an explicit
if/elif rule keyed off the decision's triggered contributing signals and a
handful of entity attributes (segment, risk level). The same inputs always
produce the same recommendations (fully traceable and reproducible), and
every list is capped at 5 (matching DI_DECISIONS.recommended_action_1..5).
"""

MAX_ACTIONS = 5


def _cap_dedupe(actions):
    seen = set()
    out = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out[:MAX_ACTIONS]


def customer_recommendations(signal_labels, segment, risk_level):
    actions = []
    if "Unresolved support tickets are elevated" in signal_labels:
        actions.append("Escalate unresolved support tickets to support leadership")
    if segment in ("Enterprise", "Mid-Market"):
        actions.append("Assign senior account manager")
    if "Renewal date is approaching soon" in signal_labels:
        actions.append("Schedule retention review ahead of renewal")
    if "Recent payments are trending late" in signal_labels or "Outstanding balance is present" in signal_labels:
        actions.append("Review renewal and commercial terms")
    if "Product usage score is low" in signal_labels or "Engagement score is low" in signal_labels:
        actions.append("Schedule customer success check-in to re-engage usage")
    if risk_level in ("High", "Critical") or not actions:
        actions.append("Start structured recovery workflow")
    return _cap_dedupe(actions)


def project_recommendations(signal_labels, risk_level):
    actions = []
    if any(s in signal_labels for s in ("Budget utilization is high", "Project is running over cost", "Actual cost exceeds budget")):
        actions.append("Conduct budget review")
    if "Completion percentage is behind expectation" in signal_labels:
        actions.append("Revise milestone plan")
    if "Planned deadline is imminent or passed" in signal_labels:
        actions.append("Escalate blockers to delivery leadership")
    if risk_level == "High":
        actions.append("Reallocate resources to accelerate delivery")
    if not actions:
        actions.append("Review project scope with customer")
    return _cap_dedupe(actions)


def finance_recommendations(signal_labels, segment, delay_probability):
    actions = ["Send payment reminder to customer"]
    if "Outstanding balance is present" in signal_labels:
        actions.append("Assign dedicated collections owner")
    if segment in ("Enterprise", "Mid-Market"):
        actions.append("Contact account manager before escalating")
    if "Customer's recent average payment delay is elevated" in signal_labels:
        actions.append("Review credit terms for this account")
    if segment == "Enterprise" and delay_probability is not None and delay_probability >= 0.5:
        actions.append("Escalate as strategic overdue account to finance leadership")
    return _cap_dedupe(actions)


def revenue_recommendations(subtype):
    mapping = {
        "FORECAST_DOWNSIDE": [
            "Review pipeline coverage for the upcoming forecast period",
            "Accelerate at-risk deals currently in negotiation",
            "Reassess quarterly revenue targets against the forecast interval",
        ],
        "REGIONAL_GROWTH": [
            "Increase regional sales investment",
            "Expand account coverage in this high-growth region",
            "Replicate this region's successful plays elsewhere",
        ],
        "SERVICE_CROSS_SELL": [
            "Launch a targeted cross-sell campaign for the antecedent-service customer base",
            "Brief account managers on this cross-sell pattern",
        ],
        "REVENUE_CONCENTRATION": [
            "Review contract terms for the largest-revenue accounts",
            "Diversify revenue base to reduce concentration risk",
            "Develop a retention plan specifically for top-concentration accounts",
        ],
    }
    return _cap_dedupe(mapping.get(subtype, ["Review signal with revenue operations team"]))


def anomaly_recommendations(entity_type):
    actions = [
        "Investigate the anomaly with the responsible account or delivery team",
        "Validate underlying data for possible data-entry or system errors",
        "Determine whether the anomaly reflects a genuine operational issue",
    ]
    if entity_type == "CUSTOMER":
        actions.append("Review recent account activity for context")
    else:
        actions.append("Review recent project activity for context")
    return _cap_dedupe(actions)
