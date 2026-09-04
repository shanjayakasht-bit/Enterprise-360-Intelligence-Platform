"""Generates PROJECT_DELIVERY decisions for at-risk, still-open projects.

Candidate population: still-open projects (status NOT IN ('Completed',
'Cancelled') -- a finished project has no forward-looking delivery
decision to make) where either Phase 1's own project_risk_category is
High/Critical, or the Phase 4 ML model separately flagged risk_level =
'High'. Same dual-signal blend as customer_decisions.py, for the same
reason: that model validated at chance-level accuracy (0.520 ROC-AUC).
"""

from decision_engine.common import (
    fetch_dataframe, get_logger, make_decision_id, model_confidence,
    normalize, run_timestamp, strategic_importance,
)
from decision_engine.priority_scoring import compute_priority
from decision_engine.recommendations import project_recommendations
from decision_engine.root_cause import PROJECT_SIGNAL_RULES, evaluate_signals, summarize_signals

logger = get_logger("project_decisions")

RISKY_POPULATION_SQL = """
SELECT p.budget
FROM ANALYTICS.VW_PROJECT_RISK p
LEFT JOIN ANALYTICS.ML_PROJECT_RISK ml ON ml.project_id = p.project_id
WHERE p.status NOT IN ('Completed', 'Cancelled')
  AND (p.project_risk_category IN ('High', 'Critical') OR ml.risk_level = 'High')
"""

CANDIDATES_SQL = """
SELECT
    p.project_id, p.customer_id, p.company_name, p.department_name,
    p.project_manager_name, p.status, p.budget, p.actual_cost, p.cost_variance,
    p.budget_utilization_pct, p.cost_overrun_pct, p.completion_pct,
    p.project_risk_score, p.project_risk_category, p.days_to_deadline,
    c360.segment,
    ml.risk_probability
FROM ANALYTICS.VW_PROJECT_RISK p
JOIN ANALYTICS.VW_CUSTOMER_360 c360 ON c360.customer_id = p.customer_id
LEFT JOIN ANALYTICS.ML_PROJECT_RISK ml ON ml.project_id = p.project_id
WHERE p.status NOT IN ('Completed', 'Cancelled')
  AND (p.project_risk_category IN ('High', 'Critical') OR ml.risk_level = 'High')
  AND p.budget >= {materiality_threshold}
"""

BUDGET_POPULATION_SQL = "SELECT PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY budget) AS p99 FROM ANALYTICS.VW_PROJECT_RISK WHERE budget > 0"

CATEGORY_SCORE = {"Low": 10.0, "Medium": 40.0, "High": 75.0, "Critical": 95.0}

# Same materiality-filtering rationale as customer_decisions.py -- top
# decile of budget exposure WITHIN the already-risky, still-open project
# population, computed live. See docs/decision_engine.md.
MATERIALITY_PERCENTILE = 0.90


def generate():
    risky_population = fetch_dataframe(RISKY_POPULATION_SQL)
    if risky_population.empty:
        logger.info("No candidate projects found")
        return []
    materiality_threshold = float(risky_population["BUDGET"].astype(float).quantile(MATERIALITY_PERCENTILE))

    df = fetch_dataframe(CANDIDATES_SQL.format(materiality_threshold=materiality_threshold))
    if df.empty:
        logger.info("No candidate projects found")
        return []

    budget_cap = float(fetch_dataframe(BUDGET_POPULATION_SQL).iloc[0, 0] or 1.0)
    confidence = model_confidence("project_risk")
    generated_at = run_timestamp()

    decisions = []
    for _, row in df.iterrows():
        row = row.to_dict()
        for col in ("BUDGET", "ACTUAL_COST", "COST_VARIANCE", "BUDGET_UTILIZATION_PCT", "COST_OVERRUN_PCT",
                     "COMPLETION_PCT", "PROJECT_RISK_SCORE", "DAYS_TO_DEADLINE", "RISK_PROBABILITY"):
            if row.get(col) is not None:
                row[col] = float(row[col])

        category = row["PROJECT_RISK_CATEGORY"]
        category_score = CATEGORY_SCORE.get(category, 50.0)
        ml_prob_pct = (row["RISK_PROBABILITY"] * 100.0) if row.get("RISK_PROBABILITY") is not None else category_score
        risk_component = 0.6 * category_score + 0.4 * ml_prob_pct

        budget = row.get("BUDGET") or 0.0
        impact_component = normalize(budget, 0, budget_cap)

        days_to_deadline = row.get("DAYS_TO_DEADLINE")
        urgency_component = normalize(days_to_deadline, 90, -30) if days_to_deadline is not None else 50.0

        strategic_component = strategic_importance(row["SEGMENT"])

        priority_score = compute_priority("PROJECT_DELIVERY", risk_component, impact_component, urgency_component, strategic_component)

        signals = evaluate_signals(row, PROJECT_SIGNAL_RULES)
        signal_labels = {label for label, _ in signals}
        why_it_happened = summarize_signals(signals)

        if row.get("RISK_PROBABILITY") is not None:
            predicted_outcome = (
                f"Model-estimated delay risk probability: {row['RISK_PROBABILITY']:.0%} "
                f"(this model validated at chance-level accuracy in Phase 4 -- treat as a weak, secondary signal)"
            )
        else:
            predicted_outcome = f"No calibrated ML risk score available for this project; classification based on business-rule risk category ({category})"

        actions = project_recommendations(signal_labels, "High" if priority_score >= 60 else "Medium")

        decisions.append({
            "DECISION_ID": make_decision_id("PROJECT_DELIVERY", "PROJECT", row["PROJECT_ID"]),
            "DECISION_TYPE": "PROJECT_DELIVERY",
            "ENTITY_TYPE": "PROJECT",
            "ENTITY_ID": row["PROJECT_ID"],
            "TITLE": f"Delivery risk: {row['PROJECT_ID']} for {row['COMPANY_NAME']} ({category})",
            "SUMMARY": f"Project for {row['COMPANY_NAME']} is {row['COMPLETION_PCT']:.0f}% complete with {category.lower()} delivery risk and ${budget:,.0f} budget exposure.",
            "SEVERITY": None,
            "PRIORITY_SCORE": priority_score,
            "WHAT_HAPPENED": f"Project {row['PROJECT_ID']} ({row['STATUS']}) has moved into the {category} risk category.",
            "WHY_IT_HAPPENED": why_it_happened,
            "PREDICTED_OUTCOME": predicted_outcome,
            "BUSINESS_IMPACT_TYPE": "BUDGET_EXPOSURE",
            "BUSINESS_IMPACT_VALUE": budget,
            "CONFIDENCE_SCORE": confidence,
            "RECOMMENDED_ACTION_1": actions[0] if len(actions) > 0 else None,
            "RECOMMENDED_ACTION_2": actions[1] if len(actions) > 1 else None,
            "RECOMMENDED_ACTION_3": actions[2] if len(actions) > 2 else None,
            "RECOMMENDED_ACTION_4": actions[3] if len(actions) > 3 else None,
            "RECOMMENDED_ACTION_5": actions[4] if len(actions) > 4 else None,
            "STATUS": "NEW",
            "GENERATED_AT": generated_at,
        })

    logger.info("Generated %d project delivery decisions", len(decisions))
    return decisions
