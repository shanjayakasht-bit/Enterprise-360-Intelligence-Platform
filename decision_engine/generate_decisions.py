"""Main Decision Intelligence Engine orchestrator. Run as:

    python -m decision_engine.generate_decisions

Process (matches the brief exactly):
  1. Read relevant analytics/mining/prediction data (each domain module)
  2. Generate candidate decisions
  3. Explain contributing signals (decision_engine/root_cause.py, inside
     each domain module)
  4. Estimate business impact (inside each domain module)
  5. Generate recommendations (decision_engine/recommendations.py)
  6. Calculate priority score (decision_engine/priority_scoring.py)
  7. Deduplicate decisions (by decision_id -- structurally unique per
     decision_type+entity_type+entity_id, checked defensively here anyway)
  8. Write DI_DECISIONS
  9. Write DI_EXECUTIVE_SUMMARY
  10. Print summary

No decision type here calls any external system, sends any message, or
modifies any source table -- every recommended_action_N is advisory text
only. No LLM is used anywhere in this module or anything it imports.
"""

import sys

import pandas as pd

from decision_engine import customer_decisions, finance_decisions, project_decisions, revenue_decisions
from decision_engine.common import (
    ENGINE_VERSION, fetch_dataframe, get_logger, make_decision_id, model_confidence,
    normalize, run_timestamp, severity_from_score, strategic_importance, write_table,
)
from decision_engine.priority_scoring import compute_priority
from decision_engine.recommendations import anomaly_recommendations

logger = get_logger("generate_decisions")

ANOMALY_DECISION_LIMIT = 10  # most severe anomalies only -- see file header and docs/decision_engine.md

CUSTOMER_ANOMALY_CONTEXT_SQL = "SELECT customer_id, company_name, segment, arr FROM ANALYTICS.VW_CUSTOMER_360"
PROJECT_ANOMALY_CONTEXT_SQL = "SELECT p.project_id, p.company_name, c360.segment, p.budget FROM ANALYTICS.VW_PROJECT_RISK p JOIN ANALYTICS.VW_CUSTOMER_360 c360 ON c360.customer_id = p.customer_id"


def generate_anomaly_decisions():
    anomalies = fetch_dataframe(f"""
        SELECT entity_type, entity_id, anomaly_type, anomaly_score, observed_value, expected_context
        FROM ANALYTICS.DM_BUSINESS_ANOMALIES
        WHERE is_anomaly = TRUE
        ORDER BY anomaly_score ASC
        LIMIT {ANOMALY_DECISION_LIMIT}
    """)
    if anomalies.empty:
        logger.info("No anomalies found")
        return []

    customer_ctx = fetch_dataframe(CUSTOMER_ANOMALY_CONTEXT_SQL).set_index("CUSTOMER_ID")
    project_ctx = fetch_dataframe(PROJECT_ANOMALY_CONTEXT_SQL).set_index("PROJECT_ID")
    max_abs_score = float(anomalies["ANOMALY_SCORE"].astype(float).abs().max()) or 1.0
    generated_at = run_timestamp()

    decisions = []
    for _, row in anomalies.iterrows():
        entity_type, entity_id = row["ENTITY_TYPE"], row["ENTITY_ID"]
        score = float(row["ANOMALY_SCORE"])

        if entity_type == "CUSTOMER" and entity_id in customer_ctx.index:
            ctx = customer_ctx.loc[entity_id]
            company_name, segment, impact_value = ctx["COMPANY_NAME"], ctx["SEGMENT"], float(ctx["ARR"] or 0)
            impact_type = "ARR_AT_RISK"
        elif entity_type == "PROJECT" and entity_id in project_ctx.index:
            ctx = project_ctx.loc[entity_id]
            company_name, segment, impact_value = ctx["COMPANY_NAME"], ctx["SEGMENT"], float(ctx["BUDGET"] or 0)
            impact_type = "BUDGET_EXPOSURE"
        else:
            company_name, segment, impact_value, impact_type = entity_id, None, 0.0, "UNKNOWN"

        risk_component = normalize(-score, 0, max_abs_score)
        impact_component = normalize(impact_value, 0, impact_value if impact_value > 0 else 1)
        urgency_component = 50.0  # anomalies have no inherent schedule; moderate default -- see priority_scoring.py
        strategic_component = strategic_importance(segment) if segment else 40.0

        priority_score = compute_priority("BUSINESS_ANOMALY", risk_component, impact_component, urgency_component, strategic_component)
        confidence = round(normalize(-score, 0, max_abs_score), 1)  # more extreme deviation -> higher confidence it's a genuine outlier

        actions = anomaly_recommendations(entity_type)
        why = f"Primary contributing signals (not claimed as definitive causes): {row['OBSERVED_VALUE']}. Population reference: {row['EXPECTED_CONTEXT']}."

        decisions.append({
            "DECISION_ID": make_decision_id("BUSINESS_ANOMALY", entity_type, entity_id),
            "DECISION_TYPE": "BUSINESS_ANOMALY",
            "ENTITY_TYPE": entity_type,
            "ENTITY_ID": entity_id,
            "TITLE": f"Investigate {row['ANOMALY_TYPE'].lower().replace('_', ' ')} anomaly: {company_name}",
            "SUMMARY": f"{entity_type.title()} {entity_id} ({company_name}) shows statistically unusual {row['ANOMALY_TYPE'].lower().replace('_', ' ')} behavior.",
            "SEVERITY": None,
            "PRIORITY_SCORE": priority_score,
            "WHAT_HAPPENED": f"{entity_type.title()} {entity_id} was flagged as a statistical outlier by Isolation Forest anomaly detection (Phase 3).",
            "WHY_IT_HAPPENED": why,
            "PREDICTED_OUTCOME": None,
            "BUSINESS_IMPACT_TYPE": impact_type,
            "BUSINESS_IMPACT_VALUE": impact_value,
            "CONFIDENCE_SCORE": confidence,
            "RECOMMENDED_ACTION_1": actions[0] if len(actions) > 0 else None,
            "RECOMMENDED_ACTION_2": actions[1] if len(actions) > 1 else None,
            "RECOMMENDED_ACTION_3": actions[2] if len(actions) > 2 else None,
            "RECOMMENDED_ACTION_4": actions[3] if len(actions) > 3 else None,
            "RECOMMENDED_ACTION_5": None,
            "STATUS": "NEW",
            "GENERATED_AT": generated_at,
        })

    logger.info("Generated %d business anomaly decisions", len(decisions))
    return decisions


def deduplicate(decisions):
    seen = {}
    duplicates = 0
    for d in decisions:
        key = d["DECISION_ID"]
        if key in seen:
            duplicates += 1
            continue
        seen[key] = d
    if duplicates:
        logger.warning("Removed %d duplicate decision_id(s)", duplicates)
    return list(seen.values())


def build_executive_summary(df):
    """Every *_at_risk / *_value metric is computed from DISTINCT entities
    (never summed across multiple decisions for the same entity), so an
    entity with two decision types contributes its exposure once -- see
    file header and docs/decision_engine.md."""
    generated_at = run_timestamp()

    critical = int((df["SEVERITY"] == "CRITICAL").sum())
    high = int((df["SEVERITY"] == "HIGH").sum())

    customer_rows = df[df["ENTITY_TYPE"] == "CUSTOMER"]
    customers_at_risk = customer_rows["ENTITY_ID"].nunique()
    # revenue_at_risk: one exposure value per distinct at-risk customer
    # (MAX across that customer's decisions, not SUM, to avoid double-
    # counting the same ARR if a customer has both a retention and an
    # anomaly decision).
    revenue_at_risk = float(
        customer_rows.groupby("ENTITY_ID")["BUSINESS_IMPACT_VALUE"].max().sum()
    ) if not customer_rows.empty else 0.0

    project_rows = df[df["ENTITY_TYPE"] == "PROJECT"]
    projects_at_risk = project_rows["ENTITY_ID"].nunique()

    invoice_rows = df[df["ENTITY_TYPE"] == "INVOICE"]
    payment_value_at_risk = float(
        invoice_rows.groupby("ENTITY_ID")["BUSINESS_IMPACT_VALUE"].max().sum()
    ) if not invoice_rows.empty else 0.0

    revenue_opportunity_rows = df[df["DECISION_TYPE"] == "REVENUE_OPPORTUNITY"]
    revenue_opportunity_value = float(
        revenue_opportunity_rows.groupby("ENTITY_ID")["BUSINESS_IMPACT_VALUE"].max().sum()
    ) if not revenue_opportunity_rows.empty else 0.0

    return pd.DataFrame([{
        "CRITICAL_DECISIONS": critical,
        "HIGH_PRIORITY_DECISIONS": high,
        "CUSTOMERS_AT_RISK": int(customers_at_risk),
        "REVENUE_AT_RISK": revenue_at_risk,
        "PROJECTS_AT_RISK": int(projects_at_risk),
        "PAYMENT_VALUE_AT_RISK": payment_value_at_risk,
        "REVENUE_OPPORTUNITY_VALUE": revenue_opportunity_value,
        "GENERATED_AT": generated_at,
    }])


def run():
    logger.info("NEXORA DECISION ENGINE -- generating decisions")

    customer = customer_decisions.generate()
    project = project_decisions.generate()
    finance = finance_decisions.generate()
    revenue = revenue_decisions.generate()
    anomaly = generate_anomaly_decisions()

    all_decisions = customer + project + finance + revenue + anomaly
    all_decisions = deduplicate(all_decisions)

    if not all_decisions:
        logger.warning("No decisions generated -- nothing to write")
        return {"total": 0}

    df = pd.DataFrame(all_decisions)
    df["SEVERITY"] = df["PRIORITY_SCORE"].apply(severity_from_score)

    write_table(df, "DI_DECISIONS")

    summary_df = build_executive_summary(df)
    write_table(summary_df, "DI_EXECUTIVE_SUMMARY")

    severity_counts = df["SEVERITY"].value_counts().to_dict()
    print("\nNEXORA DECISION ENGINE\n")
    print(f"Customer decisions: {len(customer)}")
    print(f"Project decisions: {len(project)}")
    print(f"Finance decisions: {len(finance)}")
    print(f"Revenue decisions: {len(revenue)}")
    print(f"Anomaly decisions: {len(anomaly)}")
    print()
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        print(f"{level}: {severity_counts.get(level, 0)}")
    print(f"\nTotal decisions: {len(df)}")

    return {
        "total": len(df), "customer": len(customer), "project": len(project),
        "finance": len(finance), "revenue": len(revenue), "anomaly": len(anomaly),
        "severity_counts": severity_counts,
    }


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("Decision engine run failed")
        sys.exit(1)
