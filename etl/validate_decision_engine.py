"""Validates the Phase 5 Decision Intelligence Engine outputs. Run as:

    python -m etl.validate_decision_engine
"""

import sys

from etl.snowflake_connection import get_connection

EXPECTED_RAW_STAGING_COUNTS = {
    "CUSTOMERS": 5000, "EMPLOYEES": 1000, "LEADS": 15000, "DEALS": 20000,
    "SUBSCRIPTIONS": 10000, "PROJECTS": 8000, "INVOICES": 30000, "PAYMENTS": 22777,
    "SUPPORT_TICKETS": 40000, "CUSTOMER_ACTIVITY": 50000,
}
EXPECTED_CORE_COUNTS = {
    "DIM_DATE": 4384, "DIM_REGION": 6, "DIM_DEPARTMENT": 10, "DIM_SERVICE": 16,
    "DIM_EMPLOYEE": 1001, "DIM_CUSTOMER": 5001,
    "FACT_LEADS": 15000, "FACT_DEALS": 20000, "FACT_SUBSCRIPTIONS": 10000,
    "FACT_PROJECTS": 8000, "FACT_INVOICES": 30000, "FACT_PAYMENTS": 22777,
    "FACT_SUPPORT": 40000, "FACT_CUSTOMER_ACTIVITY": 50000,
}
EXPECTED_SOURCE_COUNTS = {
    "ANALYTICS.VW_CUSTOMER_360": 5000, "ANALYTICS.VW_PROJECT_RISK": 8000,
    "ANALYTICS.DM_CUSTOMER_SEGMENTS": 5000, "ANALYTICS.DM_SERVICE_ASSOCIATIONS": 90,
    "ANALYTICS.DM_BUSINESS_ANOMALIES": 13000,
    "ANALYTICS.ML_CUSTOMER_RISK": 5000, "ANALYTICS.ML_PROJECT_RISK": 8000,
    "ANALYTICS.ML_PAYMENT_DELAY": 30000, "ANALYTICS.ML_REVENUE_FORECAST": 3,
}

PRIORITY_TO_SEVERITY = [(80, "CRITICAL"), (60, "HIGH"), (40, "MEDIUM"), (0, "LOW")]


def _expected_severity(score):
    for threshold, label in PRIORITY_TO_SEVERITY:
        if score >= threshold:
            return label
    return "LOW"


def _scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def _table_exists(cur, table):
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'ANALYTICS' AND TABLE_NAME = %s",
        (table,),
    )
    return cur.fetchone()[0] == 1


def run():
    conn = get_connection()
    checks = []
    domain_status = {}

    print("NEXORA DECISION ENGINE VALIDATION")

    try:
        cur = conn.cursor()

        # ---- 1/2. tables exist ----
        decisions_exist = _table_exists(cur, "DI_DECISIONS")
        summary_exists = _table_exists(cur, "DI_EXECUTIVE_SUMMARY")
        checks.append(("DI_DECISIONS exists", decisions_exist, "table found" if decisions_exist else "TABLE NOT FOUND"))
        checks.append(("DI_EXECUTIVE_SUMMARY exists", summary_exists, "table found" if summary_exists else "TABLE NOT FOUND"))
        tables_pass = decisions_exist and summary_exists
        print(f"\nDecision tables: {'PASS' if tables_pass else 'FAIL'}")

        if not decisions_exist:
            raise RuntimeError("DI_DECISIONS missing, cannot continue validation")

        cur.execute("SELECT decision_type, entity_type, entity_id, priority_score, severity, "
                     "what_happened, why_it_happened, predicted_outcome, recommended_action_1, "
                     "business_impact_value, confidence_score FROM ANALYTICS.DI_DECISIONS")
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
        decisions = [dict(zip(cols, r)) for r in rows]
        total = len(decisions)

        # ---- 3. decision_id unique ----
        total_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.DI_DECISIONS")
        distinct_ids = _scalar(cur, "SELECT COUNT(DISTINCT decision_id) FROM ANALYTICS.DI_DECISIONS")
        checks.append(("decision_id is unique", total_rows == distinct_ids, f"rows={total_rows} distinct={distinct_ids}"))

        # ---- 5. priority_score bounds ----
        bad_priority = sum(1 for d in decisions if d["PRIORITY_SCORE"] is None or not (0 <= d["PRIORITY_SCORE"] <= 100))
        checks.append(("priority_score between 0 and 100", bad_priority == 0, f"{bad_priority} out-of-range rows"))

        # ---- 6. severity matches thresholds ----
        mismatched_severity = sum(
            1 for d in decisions
            if d["PRIORITY_SCORE"] is not None and d["SEVERITY"] != _expected_severity(float(d["PRIORITY_SCORE"]))
        )
        checks.append(("severity matches priority score thresholds", mismatched_severity == 0, f"{mismatched_severity} mismatched rows"))

        # ---- 7/8/9/10. required text fields ----
        missing_what = sum(1 for d in decisions if not d["WHAT_HAPPENED"])
        missing_why = sum(1 for d in decisions if not d["WHY_IT_HAPPENED"])
        checks.append(("every decision has WHAT happened", missing_what == 0, f"{missing_what} missing"))
        checks.append(("every decision has WHY / contributing signals", missing_why == 0, f"{missing_why} missing"))

        applicable_prediction_types = ("CUSTOMER_RETENTION", "PROJECT_DELIVERY", "PAYMENT_COLLECTION")
        missing_prediction = sum(
            1 for d in decisions if d["DECISION_TYPE"] in applicable_prediction_types and not d["PREDICTED_OUTCOME"]
        )
        checks.append(("every applicable decision has predicted outcome", missing_prediction == 0, f"{missing_prediction} missing (of types {applicable_prediction_types})"))

        missing_action = sum(1 for d in decisions if not d["RECOMMENDED_ACTION_1"])
        checks.append(("every decision has at least one recommended action", missing_action == 0, f"{missing_action} missing"))

        # ---- 11. financial impact non-negative ----
        negative_impact = sum(1 for d in decisions if d["BUSINESS_IMPACT_VALUE"] is not None and float(d["BUSINESS_IMPACT_VALUE"]) < 0)
        checks.append(("financial impact is non-negative", negative_impact == 0, f"{negative_impact} negative rows"))

        # ---- 4. entity identifiers resolve ----
        invalid_customer = _scalar(cur, """
            SELECT COUNT(*) FROM ANALYTICS.DI_DECISIONS d
            WHERE d.entity_type = 'CUSTOMER'
              AND NOT EXISTS (SELECT 1 FROM CORE.DIM_CUSTOMER c WHERE c.customer_id = d.entity_id AND c.is_current = TRUE)
        """)
        invalid_project = _scalar(cur, """
            SELECT COUNT(*) FROM ANALYTICS.DI_DECISIONS d
            WHERE d.entity_type = 'PROJECT'
              AND NOT EXISTS (SELECT 1 FROM CORE.FACT_PROJECTS p WHERE p.project_id = d.entity_id)
        """)
        invalid_invoice = _scalar(cur, """
            SELECT COUNT(*) FROM ANALYTICS.DI_DECISIONS d
            WHERE d.entity_type = 'INVOICE'
              AND NOT EXISTS (SELECT 1 FROM CORE.FACT_INVOICES i WHERE i.invoice_id = d.entity_id)
        """)
        checks.append(("CUSTOMER entity identifiers resolve", invalid_customer == 0, f"{invalid_customer} invalid"))
        checks.append(("PROJECT entity identifiers resolve", invalid_project == 0, f"{invalid_project} invalid"))
        checks.append(("INVOICE entity identifiers resolve", invalid_invoice == 0, f"{invalid_invoice} invalid"))

        # ---- 12. no duplicate active decision for identical type+entity_type+entity_id ----
        dup_keys = _scalar(cur, """
            SELECT COUNT(*) FROM (
                SELECT decision_type, entity_type, entity_id FROM ANALYTICS.DI_DECISIONS
                GROUP BY decision_type, entity_type, entity_id HAVING COUNT(*) > 1
            )
        """)
        checks.append(("no duplicate active decision for identical type+entity_type+entity_id", dup_keys == 0, f"{dup_keys} duplicate keys"))

        # ---- 13/14/15. reconciliation with source ML tables ----
        for decision_type, entity_col, ml_table, ml_col in [
            ("CUSTOMER_RETENTION", "entity_id", "ML_CUSTOMER_RISK", "customer_id"),
            ("PROJECT_DELIVERY", "entity_id", "ML_PROJECT_RISK", "project_id"),
            ("PAYMENT_COLLECTION", "entity_id", "ML_PAYMENT_DELAY", "invoice_id"),
        ]:
            unresolved = _scalar(cur, f"""
                SELECT COUNT(*) FROM ANALYTICS.DI_DECISIONS d
                WHERE d.decision_type = '{decision_type}'
                  AND NOT EXISTS (SELECT 1 FROM ANALYTICS.{ml_table} m WHERE m.{ml_col} = d.{entity_col})
            """)
            checks.append((f"{decision_type} decisions reconcile with {ml_table}", unresolved == 0, f"{unresolved} unresolved"))

        # ---- 16. revenue decisions reconcile with forecast data (where applicable) ----
        forecast_decisions = [d for d in decisions if d["DECISION_TYPE"] == "REVENUE_OPPORTUNITY" and str(d["ENTITY_ID"] or "").startswith("FORECAST_")]
        forecast_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_REVENUE_FORECAST")
        forecast_ok = (not forecast_decisions) or forecast_rows > 0
        checks.append(("revenue forecast decisions reconcile with ML_REVENUE_FORECAST", forecast_ok,
                        f"{len(forecast_decisions)} forecast-based decisions, {forecast_rows} forecast rows available"))

        # ---- domain PASS/FAIL summary ----
        for label, decision_type in [
            ("Customer Decisions", "CUSTOMER_RETENTION"), ("Project Decisions", "PROJECT_DELIVERY"),
            ("Finance Decisions", "PAYMENT_COLLECTION"), ("Revenue Decisions", "REVENUE_OPPORTUNITY"),
            ("Anomaly Decisions", "BUSINESS_ANOMALY"),
        ]:
            subset = [d for d in decisions if d["DECISION_TYPE"] == decision_type]
            ok = all(d["WHAT_HAPPENED"] and d["WHY_IT_HAPPENED"] and d["RECOMMENDED_ACTION_1"]
                     and d["PRIORITY_SCORE"] is not None and 0 <= float(d["PRIORITY_SCORE"]) <= 100 for d in subset)
            domain_status[label] = ok

        # ---- 17. executive summary reconciles ----
        cur.execute("SELECT critical_decisions, high_priority_decisions, customers_at_risk, revenue_at_risk, "
                     "projects_at_risk, payment_value_at_risk, revenue_opportunity_value FROM ANALYTICS.DI_EXECUTIVE_SUMMARY")
        summary_row = cur.fetchone()
        if summary_row:
            summary_cols = [c[0] for c in cur.description]
            summary = dict(zip(summary_cols, summary_row))

            actual_critical = sum(1 for d in decisions if d["SEVERITY"] == "CRITICAL")
            actual_high = sum(1 for d in decisions if d["SEVERITY"] == "HIGH")
            checks.append(("executive summary critical_decisions reconciles", summary["CRITICAL_DECISIONS"] == actual_critical,
                            f"summary={summary['CRITICAL_DECISIONS']} actual={actual_critical}"))
            checks.append(("executive summary high_priority_decisions reconciles", summary["HIGH_PRIORITY_DECISIONS"] == actual_high,
                            f"summary={summary['HIGH_PRIORITY_DECISIONS']} actual={actual_high}"))

            actual_customers_at_risk = len({d["ENTITY_ID"] for d in decisions if d["ENTITY_TYPE"] == "CUSTOMER"})
            actual_projects_at_risk = len({d["ENTITY_ID"] for d in decisions if d["ENTITY_TYPE"] == "PROJECT"})
            checks.append(("executive summary customers_at_risk reconciles", summary["CUSTOMERS_AT_RISK"] == actual_customers_at_risk,
                            f"summary={summary['CUSTOMERS_AT_RISK']} actual={actual_customers_at_risk}"))
            checks.append(("executive summary projects_at_risk reconciles", summary["PROJECTS_AT_RISK"] == actual_projects_at_risk,
                            f"summary={summary['PROJECTS_AT_RISK']} actual={actual_projects_at_risk}"))
        else:
            checks.append(("executive summary reconciles", False, "no row in DI_EXECUTIVE_SUMMARY"))

        # ---- 18. source tables unchanged ----
        for table, expected in EXPECTED_RAW_STAGING_COUNTS.items():
            raw_rows = _scalar(cur, f"SELECT COUNT(*) FROM RAW.{table}")
            stg_rows = _scalar(cur, f"SELECT COUNT(*) FROM STAGING.STG_{table}")
            checks.append((f"RAW.{table} unchanged", raw_rows == expected, f"expected {expected}, found {raw_rows}"))
            checks.append((f"STAGING.STG_{table} unchanged", stg_rows == expected, f"expected {expected}, found {stg_rows}"))
        for table, expected in EXPECTED_CORE_COUNTS.items():
            core_rows = _scalar(cur, f"SELECT COUNT(*) FROM CORE.{table}")
            checks.append((f"CORE.{table} unchanged", core_rows == expected, f"expected {expected}, found {core_rows}"))
        for table, expected in EXPECTED_SOURCE_COUNTS.items():
            rows_ = _scalar(cur, f"SELECT COUNT(*) FROM {table}")
            checks.append((f"{table} unchanged", rows_ == expected, f"expected {expected}, found {rows_}"))
    finally:
        conn.close()

    severity_counts = {}
    if decisions_exist:
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            severity_counts[level] = sum(1 for d in decisions if d["SEVERITY"] == level)

    print(f"\nTotal Decisions: {total if decisions_exist else 0}")
    print(f"Critical: {severity_counts.get('CRITICAL', 0)}")
    print(f"High: {severity_counts.get('HIGH', 0)}")
    print(f"Medium: {severity_counts.get('MEDIUM', 0)}")
    print(f"Low: {severity_counts.get('LOW', 0)}")

    print()
    for label in ("Customer Decisions", "Project Decisions", "Finance Decisions", "Revenue Decisions", "Anomaly Decisions"):
        print(f"{label}: {'PASS' if domain_status.get(label) else 'FAIL'}")

    print("\n" + "=" * 60)
    print("Detailed checks:")
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print("-" * 60)
    passed_count = sum(1 for _, p, _ in checks if p)
    failed_count = len(checks) - passed_count
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print("=" * 60)

    return failed_count == 0 and all(domain_status.values())


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
