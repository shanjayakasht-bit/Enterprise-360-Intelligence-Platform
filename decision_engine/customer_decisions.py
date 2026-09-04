"""Generates CUSTOMER_RETENTION decisions for at-risk customers.

Candidate population: customers where Phase 1's own business-rule risk
classification (VW_CUSTOMER_HEALTH.churn_risk_category, a transparent,
already-validated formula -- see docs/predictive_analytics.md) is High or
Critical, UNION customers the Phase 4 ML model separately flagged
risk_level = 'High'. Both signals are surfaced; the risk component blends
them 60/40 in favor of the business-rule category, since Phase 4 validated
that model at chance-level accuracy (confidence_score reflects this
honestly -- see decision_engine/common.py::model_confidence).
"""

import pandas as pd

from decision_engine.common import (
    fetch_dataframe, get_logger, make_decision_id, model_confidence,
    normalize, run_timestamp, strategic_importance,
)
from decision_engine.priority_scoring import compute_priority
from decision_engine.recommendations import customer_recommendations
from decision_engine.root_cause import CUSTOMER_SIGNAL_RULES, evaluate_signals, summarize_signals

logger = get_logger("customer_decisions")

RISKY_POPULATION_SQL = """
SELECT c360.arr
FROM ANALYTICS.VW_CUSTOMER_HEALTH h
JOIN ANALYTICS.VW_CUSTOMER_360 c360 ON c360.customer_id = h.customer_id
LEFT JOIN ANALYTICS.ML_CUSTOMER_RISK ml ON ml.customer_id = h.customer_id
WHERE h.churn_risk_category IN ('High', 'Critical')
   OR ml.risk_level = 'High'
"""

CANDIDATES_SQL = """
SELECT
    h.customer_id, h.company_name, h.segment, h.region_name,
    h.churn_risk_category, h.risk_classification,
    h.product_usage_score, h.engagement_score, h.satisfaction_score,
    h.support_ticket_count_recent, h.open_ticket_count, h.avg_payment_delay_days,
    h.outstanding_amount, h.days_to_renewal,
    c360.total_revenue, c360.arr, c360.sla_breaches, c360.project_risk,
    ml.risk_probability
FROM ANALYTICS.VW_CUSTOMER_HEALTH h
JOIN ANALYTICS.VW_CUSTOMER_360 c360 ON c360.customer_id = h.customer_id
LEFT JOIN ANALYTICS.ML_CUSTOMER_RISK ml ON ml.customer_id = h.customer_id
WHERE (h.churn_risk_category IN ('High', 'Critical') OR ml.risk_level = 'High')
  AND c360.arr >= {materiality_threshold}
"""

ARR_POPULATION_SQL = "SELECT PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY arr) AS p99 FROM ANALYTICS.VW_CUSTOMER_360 WHERE arr > 0"

CATEGORY_SCORE = {"Low": 10.0, "Medium": 40.0, "High": 75.0, "Critical": 95.0}

# Materiality filter: being risky is not sufficient on its own to warrant a
# top-level decision card -- restrict to the top decile of ARR exposure
# WITHIN the already-risky population (computed live, not a guessed
# number), so the engine focuses finite attention on the highest-exposure
# at-risk accounts first. Lower-exposure risky customers remain fully
# visible in VW_CUSTOMER_HEALTH/ML_CUSTOMER_RISK -- they are not hidden,
# just not promoted to an executive decision. See docs/decision_engine.md.
MATERIALITY_PERCENTILE = 0.90


def generate():
    risky_population = fetch_dataframe(RISKY_POPULATION_SQL)
    if risky_population.empty:
        logger.info("No candidate customers found")
        return []
    materiality_threshold = float(risky_population["ARR"].astype(float).quantile(MATERIALITY_PERCENTILE))

    df = fetch_dataframe(CANDIDATES_SQL.format(materiality_threshold=materiality_threshold))
    if df.empty:
        logger.info("No candidate customers found")
        return []

    arr_cap = float(fetch_dataframe(ARR_POPULATION_SQL).iloc[0, 0] or 1.0)
    confidence = model_confidence("customer_churn")
    generated_at = run_timestamp()

    decisions = []
    for _, row in df.iterrows():
        row = row.to_dict()
        for col in ("PRODUCT_USAGE_SCORE", "ENGAGEMENT_SCORE", "SATISFACTION_SCORE", "OPEN_TICKET_COUNT",
                     "AVG_PAYMENT_DELAY_DAYS", "OUTSTANDING_AMOUNT", "DAYS_TO_RENEWAL", "ARR", "RISK_PROBABILITY"):
            if row.get(col) is not None:
                row[col] = float(row[col])
        row["AVG_PAYMENT_DELAY_DAYS"] = row.get("AVG_PAYMENT_DELAY_DAYS") or 0.0
        row["OUTSTANDING_AMOUNT"] = row.get("OUTSTANDING_AMOUNT") or 0.0

        category = row["CHURN_RISK_CATEGORY"]
        category_score = CATEGORY_SCORE.get(category, 50.0)
        ml_prob_pct = (row["RISK_PROBABILITY"] * 100.0) if row.get("RISK_PROBABILITY") is not None else category_score
        risk_component = 0.6 * category_score + 0.4 * ml_prob_pct

        arr = row.get("ARR") or 0.0
        impact_component = normalize(arr, 0, arr_cap)

        days_to_renewal = row.get("DAYS_TO_RENEWAL")
        urgency_component = normalize(days_to_renewal, 365, 0) if days_to_renewal is not None else 30.0

        strategic_component = strategic_importance(row["SEGMENT"])

        priority_score = compute_priority("CUSTOMER_RETENTION", risk_component, impact_component, urgency_component, strategic_component)

        signals = evaluate_signals(row, CUSTOMER_SIGNAL_RULES)
        signal_labels = {label for label, _ in signals}
        why_it_happened = summarize_signals(signals)

        if row.get("RISK_PROBABILITY") is not None:
            predicted_outcome = (
                f"Model-estimated churn risk probability: {row['RISK_PROBABILITY']:.0%} "
                f"(this model validated at chance-level accuracy in Phase 4 -- treat as a weak, secondary signal)"
            )
        else:
            predicted_outcome = f"No calibrated ML risk score available for this customer; classification based on business-rule risk category ({category})"

        actions = customer_recommendations(signal_labels, row["SEGMENT"], row["RISK_CLASSIFICATION"])

        decisions.append({
            "DECISION_ID": make_decision_id("CUSTOMER_RETENTION", "CUSTOMER", row["CUSTOMER_ID"]),
            "DECISION_TYPE": "CUSTOMER_RETENTION",
            "ENTITY_TYPE": "CUSTOMER",
            "ENTITY_ID": row["CUSTOMER_ID"],
            "TITLE": f"Retention risk: {row['COMPANY_NAME']} ({row['RISK_CLASSIFICATION']})",
            "SUMMARY": f"{row['COMPANY_NAME']} ({row['SEGMENT']}) shows {row['RISK_CLASSIFICATION'].lower()} account health with ${arr:,.0f} ARR exposure.",
            "SEVERITY": None,  # filled by generate_decisions.py from priority_score
            "PRIORITY_SCORE": priority_score,
            "WHAT_HAPPENED": f"Customer engagement and account health indicators for {row['COMPANY_NAME']} have declined into the {category} risk category.",
            "WHY_IT_HAPPENED": why_it_happened,
            "PREDICTED_OUTCOME": predicted_outcome,
            "BUSINESS_IMPACT_TYPE": "ARR_AT_RISK",
            "BUSINESS_IMPACT_VALUE": arr,
            "CONFIDENCE_SCORE": confidence,
            "RECOMMENDED_ACTION_1": actions[0] if len(actions) > 0 else None,
            "RECOMMENDED_ACTION_2": actions[1] if len(actions) > 1 else None,
            "RECOMMENDED_ACTION_3": actions[2] if len(actions) > 2 else None,
            "RECOMMENDED_ACTION_4": actions[3] if len(actions) > 3 else None,
            "RECOMMENDED_ACTION_5": actions[4] if len(actions) > 4 else None,
            "STATUS": "NEW",
            "GENERATED_AT": generated_at,
        })

    logger.info("Generated %d customer retention decisions", len(decisions))
    return decisions
