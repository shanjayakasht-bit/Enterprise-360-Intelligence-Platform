"""Generates PAYMENT_COLLECTION decisions for at-risk unpaid/overdue invoices.

Candidate population: invoices with an actual outstanding balance (status
IN ('Unpaid','Overdue','Partially Paid') AND outstanding_amount > 0) that
the Phase 4 payment-delay model flagged risk_level = 'High'. Unlike the
customer/project models, that model validated with REAL signal (ROC-AUC
0.721 -- see docs/predictive_analytics.md), so its probability is used
directly as the risk component here, not diluted with a secondary
business-rule score the way the two weaker models are.

Recommendations are advisory only -- this module never sends a reminder,
never contacts anyone, and never modifies any invoice or payment record.
"""

from decision_engine.common import (
    fetch_dataframe, get_logger, make_decision_id, model_confidence,
    normalize, run_timestamp, strategic_importance,
)
from decision_engine.priority_scoring import compute_priority
from decision_engine.recommendations import finance_recommendations
from decision_engine.root_cause import PAYMENT_SIGNAL_RULES, evaluate_signals, summarize_signals

logger = get_logger("finance_decisions")

# REFERENCE_DATE = 2026-09-04, mirrors config.settings.REFERENCE_DATE (Phase 1)
# and the same literal already used in Phase 2D's VW_PROJECT_RISK -- see that
# phase's documentation for why a fixed "today" is used instead of live
# CURRENT_DATE() throughout this warehouse.
RISKY_POPULATION_SQL = """
SELECT f.outstanding_amount
FROM ANALYTICS.VW_FINANCE_SUMMARY f
JOIN ANALYTICS.ML_PAYMENT_DELAY ml ON ml.invoice_id = f.invoice_id
WHERE f.status IN ('Unpaid', 'Overdue', 'Partially Paid')
  AND f.outstanding_amount > 0
  AND ml.risk_level = 'High'
"""

CANDIDATES_SQL = """
SELECT
    f.invoice_id, f.customer_id, f.company_name, f.region_name,
    f.status, f.total_amount, f.outstanding_amount, f.avg_payment_delay_days,
    DATEDIFF('day', f.due_date, '2026-09-04'::DATE) AS days_overdue,
    c360.segment,
    ml.delay_probability
FROM ANALYTICS.VW_FINANCE_SUMMARY f
JOIN ANALYTICS.VW_CUSTOMER_360 c360 ON c360.customer_id = f.customer_id
JOIN ANALYTICS.ML_PAYMENT_DELAY ml ON ml.invoice_id = f.invoice_id
WHERE f.status IN ('Unpaid', 'Overdue', 'Partially Paid')
  AND f.outstanding_amount >= {materiality_threshold}
  AND ml.risk_level = 'High'
"""

OUTSTANDING_POPULATION_SQL = "SELECT PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY outstanding_amount) AS p99 FROM ANALYTICS.VW_FINANCE_SUMMARY WHERE outstanding_amount > 0"

# Same materiality-filtering rationale as customer_decisions.py -- top
# decile of outstanding-balance exposure WITHIN the already-risky invoice
# population, computed live. See docs/decision_engine.md.
MATERIALITY_PERCENTILE = 0.90


def generate():
    risky_population = fetch_dataframe(RISKY_POPULATION_SQL)
    if risky_population.empty:
        logger.info("No candidate invoices found")
        return []
    materiality_threshold = float(risky_population["OUTSTANDING_AMOUNT"].astype(float).quantile(MATERIALITY_PERCENTILE))

    df = fetch_dataframe(CANDIDATES_SQL.format(materiality_threshold=materiality_threshold))
    if df.empty:
        logger.info("No candidate invoices found")
        return []

    outstanding_cap = float(fetch_dataframe(OUTSTANDING_POPULATION_SQL).iloc[0, 0] or 1.0)
    confidence = model_confidence("payment_delay")
    generated_at = run_timestamp()

    decisions = []
    for _, row in df.iterrows():
        row = row.to_dict()
        for col in ("TOTAL_AMOUNT", "OUTSTANDING_AMOUNT", "AVG_PAYMENT_DELAY_DAYS", "DAYS_OVERDUE", "DELAY_PROBABILITY"):
            if row.get(col) is not None:
                row[col] = float(row[col])
        row["AVG_PAYMENT_DELAY_DAYS"] = row.get("AVG_PAYMENT_DELAY_DAYS") or 0.0

        delay_probability = row["DELAY_PROBABILITY"]
        risk_component = delay_probability * 100.0

        outstanding = row["OUTSTANDING_AMOUNT"]
        impact_component = normalize(outstanding, 0, outstanding_cap)

        days_overdue = row.get("DAYS_OVERDUE") or 0.0
        urgency_component = normalize(days_overdue, 0, 90)

        strategic_component = strategic_importance(row["SEGMENT"])

        priority_score = compute_priority("PAYMENT_COLLECTION", risk_component, impact_component, urgency_component, strategic_component)

        signals = evaluate_signals(row, PAYMENT_SIGNAL_RULES)
        signal_labels = {label for label, _ in signals}
        why_it_happened = summarize_signals(signals)

        predicted_outcome = f"Model-estimated probability this invoice is/becomes a late payment: {delay_probability:.0%}"

        actions = finance_recommendations(signal_labels, row["SEGMENT"], delay_probability)

        decisions.append({
            "DECISION_ID": make_decision_id("PAYMENT_COLLECTION", "INVOICE", row["INVOICE_ID"]),
            "DECISION_TYPE": "PAYMENT_COLLECTION",
            "ENTITY_TYPE": "INVOICE",
            "ENTITY_ID": row["INVOICE_ID"],
            "TITLE": f"Collection priority: invoice {row['INVOICE_ID']} for {row['COMPANY_NAME']}",
            "SUMMARY": f"Invoice {row['INVOICE_ID']} ({row['STATUS']}) for {row['COMPANY_NAME']} has ${outstanding:,.0f} outstanding with {delay_probability:.0%} predicted delay risk.",
            "SEVERITY": None,
            "PRIORITY_SCORE": priority_score,
            "WHAT_HAPPENED": f"Invoice {row['INVOICE_ID']} for {row['COMPANY_NAME']} is {row['STATUS'].lower()} with an outstanding balance, {days_overdue:.0f} days past due date.",
            "WHY_IT_HAPPENED": why_it_happened,
            "PREDICTED_OUTCOME": predicted_outcome,
            "BUSINESS_IMPACT_TYPE": "INVOICE_AT_RISK",
            "BUSINESS_IMPACT_VALUE": outstanding,
            "CONFIDENCE_SCORE": confidence,
            "RECOMMENDED_ACTION_1": actions[0] if len(actions) > 0 else None,
            "RECOMMENDED_ACTION_2": actions[1] if len(actions) > 1 else None,
            "RECOMMENDED_ACTION_3": actions[2] if len(actions) > 2 else None,
            "RECOMMENDED_ACTION_4": actions[3] if len(actions) > 3 else None,
            "RECOMMENDED_ACTION_5": actions[4] if len(actions) > 4 else None,
            "STATUS": "NEW",
            "GENERATED_AT": generated_at,
        })

    logger.info("Generated %d payment collection decisions", len(decisions))
    return decisions
