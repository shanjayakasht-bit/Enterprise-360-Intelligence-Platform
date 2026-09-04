"""Validates the Phase 4 predictive analytics outputs. Run as:

    python -m etl.validate_predictions

Checks each of the four prediction tables (existence, probability bounds,
valid entity IDs, no duplicates, evaluation metrics present), the revenue
forecast's chronological/non-negative/unique-date properties, that local
row-count expectations reconcile with what's in Snowflake, and that every
RAW/STAGING/CORE/ANALYTICS source object remains unchanged.
"""

import json
import sys
from pathlib import Path

from etl.snowflake_connection import get_connection

ROOT_DIR = Path(__file__).resolve().parent.parent
METRICS_DIR = ROOT_DIR / "artifacts" / "metrics"

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
EXPECTED_ANALYTICS_COUNTS = {"VW_CUSTOMER_360": 5000, "VW_PROJECT_RISK": 8000, "VW_REVENUE_TRENDS": None}


def _scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def _table_exists(cur, table):
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'ANALYTICS' AND TABLE_NAME = %s",
        (table,),
    )
    return cur.fetchone()[0] == 1


def _load_metrics(name):
    path = METRICS_DIR / f"{name}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run():
    conn = get_connection()
    checks = []
    model_summaries = {}

    print("NEXORA PREDICTIVE ANALYTICS VALIDATION")

    try:
        cur = conn.cursor()

        # ============================================================
        # Customer Risk Model
        # ============================================================
        exists = _table_exists(cur, "ML_CUSTOMER_RISK")
        checks.append(("ML_CUSTOMER_RISK exists", exists, "table found" if exists else "TABLE NOT FOUND"))
        cm = _load_metrics("customer_churn")
        checks.append(("Customer risk evaluation metrics exist", cm is not None,
                        "artifacts/metrics/customer_churn.json found" if cm else "MISSING"))

        if exists:
            n = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_CUSTOMER_RISK")
            n_distinct = _scalar(cur, "SELECT COUNT(DISTINCT customer_id) FROM ANALYTICS.ML_CUSTOMER_RISK")
            prob_ok = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_CUSTOMER_RISK WHERE risk_probability < 0 OR risk_probability > 1") == 0
            invalid_ids = _scalar(cur, """
                SELECT COUNT(*) FROM ANALYTICS.ML_CUSTOMER_RISK r
                WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_CUSTOMER c WHERE c.customer_id = r.customer_id AND c.is_current = TRUE)
            """)
            checks.append(("Customer risk predictions exist", n > 0, f"{n} rows"))
            checks.append(("Customer risk: no duplicate customer_id", n == n_distinct, f"rows={n} distinct={n_distinct}"))
            checks.append(("Customer risk: probabilities in [0,1]", prob_ok, "all in range" if prob_ok else "out-of-range values found"))
            checks.append(("Customer risk: customer IDs valid", invalid_ids == 0, f"{invalid_ids} invalid IDs"))
            model_summaries["customer"] = {
                "algorithm": cm["selected_algorithm"] if cm else None,
                "roc_auc": cm["algorithms_compared"][cm["selected_algorithm"]]["roc_auc"] if cm else None,
                "f1": cm["algorithms_compared"][cm["selected_algorithm"]]["f1"] if cm else None,
            }

        # ============================================================
        # Project Risk Model
        # ============================================================
        exists = _table_exists(cur, "ML_PROJECT_RISK")
        checks.append(("ML_PROJECT_RISK exists", exists, "table found" if exists else "TABLE NOT FOUND"))
        pm = _load_metrics("project_risk")
        checks.append(("Project risk evaluation metrics exist", pm is not None,
                        "artifacts/metrics/project_risk.json found" if pm else "MISSING"))

        if exists:
            n = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_PROJECT_RISK")
            n_distinct = _scalar(cur, "SELECT COUNT(DISTINCT project_id) FROM ANALYTICS.ML_PROJECT_RISK")
            prob_ok = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_PROJECT_RISK WHERE risk_probability < 0 OR risk_probability > 1") == 0
            invalid_ids = _scalar(cur, """
                SELECT COUNT(*) FROM ANALYTICS.ML_PROJECT_RISK r
                WHERE NOT EXISTS (SELECT 1 FROM CORE.FACT_PROJECTS p WHERE p.project_id = r.project_id)
            """)
            checks.append(("Project risk: no duplicate project_id", n == n_distinct, f"rows={n} distinct={n_distinct}"))
            checks.append(("Project risk: probabilities in [0,1]", prob_ok, "all in range" if prob_ok else "out-of-range values found"))
            checks.append(("Project risk: project IDs valid", invalid_ids == 0, f"{invalid_ids} invalid IDs"))
            model_summaries["project"] = {
                "algorithm": pm["selected_algorithm"] if pm else None,
                "roc_auc": pm["algorithms_compared"][pm["selected_algorithm"]]["roc_auc"] if pm else None,
                "f1": pm["algorithms_compared"][pm["selected_algorithm"]]["f1"] if pm else None,
            }

        # ============================================================
        # Payment Delay Model
        # ============================================================
        exists = _table_exists(cur, "ML_PAYMENT_DELAY")
        checks.append(("ML_PAYMENT_DELAY exists", exists, "table found" if exists else "TABLE NOT FOUND"))
        pdm = _load_metrics("payment_delay")
        checks.append(("Payment delay evaluation metrics exist", pdm is not None,
                        "artifacts/metrics/payment_delay.json found" if pdm else "MISSING"))

        if exists:
            n = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_PAYMENT_DELAY")
            n_distinct = _scalar(cur, "SELECT COUNT(DISTINCT invoice_id) FROM ANALYTICS.ML_PAYMENT_DELAY")
            prob_ok = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_PAYMENT_DELAY WHERE delay_probability < 0 OR delay_probability > 1") == 0
            invalid_ids = _scalar(cur, """
                SELECT COUNT(*) FROM ANALYTICS.ML_PAYMENT_DELAY r
                WHERE NOT EXISTS (SELECT 1 FROM CORE.FACT_INVOICES i WHERE i.invoice_id = r.invoice_id)
            """)
            checks.append(("Payment delay: no duplicate invoice_id", n == n_distinct, f"rows={n} distinct={n_distinct}"))
            checks.append(("Payment delay: probabilities in [0,1]", prob_ok, "all in range" if prob_ok else "out-of-range values found"))
            checks.append(("Payment delay: invoice IDs valid", invalid_ids == 0, f"{invalid_ids} invalid IDs"))
            model_summaries["payment"] = {
                "algorithm": pdm["selected_algorithm"] if pdm else None,
                "roc_auc": pdm["algorithms_compared"][pdm["selected_algorithm"]]["roc_auc"] if pdm else None,
                "f1": pdm["algorithms_compared"][pdm["selected_algorithm"]]["f1"] if pdm else None,
            }

        # ============================================================
        # Revenue Forecast
        # ============================================================
        exists = _table_exists(cur, "ML_REVENUE_FORECAST")
        checks.append(("ML_REVENUE_FORECAST exists", exists, "table found" if exists else "TABLE NOT FOUND"))
        rm = _load_metrics("revenue_forecast")
        checks.append(("Revenue forecast evaluation metrics exist", rm is not None,
                        "artifacts/metrics/revenue_forecast.json found" if rm else "MISSING"))

        if exists:
            n = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_REVENUE_FORECAST")
            n_distinct = _scalar(cur, "SELECT COUNT(DISTINCT forecast_date) FROM ANALYTICS.ML_REVENUE_FORECAST")
            non_negative = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_REVENUE_FORECAST WHERE predicted_revenue < 0") == 0
            checks.append(("Revenue forecast: dates unique", n == n_distinct, f"rows={n} distinct_dates={n_distinct}"))
            checks.append(("Revenue forecast: predicted_revenue non-negative", non_negative,
                            "all >= 0" if non_negative else "negative values found"))

            future_ok = True
            if rm:
                train_end = rm["train_period"][1]
                cur.execute("SELECT MIN(forecast_date) FROM ANALYTICS.ML_REVENUE_FORECAST")
                min_forecast_date = str(cur.fetchone()[0])
                future_ok = min_forecast_date > train_end
                checks.append(("Revenue forecast: dates are future relative to training period", future_ok,
                                f"train_end={train_end} min_forecast_date={min_forecast_date}"))
                checks.append(("Revenue forecast: chronological split confirmed", bool(rm.get("chronological_split")),
                                f"chronological_split={rm.get('chronological_split')}"))
            model_summaries["revenue"] = {
                "method": rm["selected_method"] if rm else None,
                "mae": rm["methods_compared"][rm["selected_method"]]["mae"] if rm else None,
                "rmse": rm["methods_compared"][rm["selected_method"]]["rmse"] if rm else None,
            }

        # ============================================================
        # Database: row-count reconciliation + source unchanged
        # ============================================================
        expected_customer_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.VW_CUSTOMER_360")
        actual_customer_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_CUSTOMER_RISK")
        checks.append(("ML_CUSTOMER_RISK row count matches VW_CUSTOMER_360", actual_customer_rows == expected_customer_rows,
                        f"table={actual_customer_rows} VW_CUSTOMER_360={expected_customer_rows}"))

        expected_project_rows = _scalar(cur, "SELECT COUNT(*) FROM CORE.FACT_PROJECTS")
        actual_project_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_PROJECT_RISK")
        checks.append(("ML_PROJECT_RISK row count matches FACT_PROJECTS", actual_project_rows == expected_project_rows,
                        f"table={actual_project_rows} FACT_PROJECTS={expected_project_rows}"))

        expected_invoice_rows = _scalar(cur, "SELECT COUNT(*) FROM CORE.FACT_INVOICES")
        actual_invoice_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.ML_PAYMENT_DELAY")
        checks.append(("ML_PAYMENT_DELAY row count matches FACT_INVOICES", actual_invoice_rows == expected_invoice_rows,
                        f"table={actual_invoice_rows} FACT_INVOICES={expected_invoice_rows}"))

        for table, expected in EXPECTED_RAW_STAGING_COUNTS.items():
            raw_rows = _scalar(cur, f"SELECT COUNT(*) FROM RAW.{table}")
            stg_rows = _scalar(cur, f"SELECT COUNT(*) FROM STAGING.STG_{table}")
            checks.append((f"RAW.{table} unchanged", raw_rows == expected, f"expected {expected}, found {raw_rows}"))
            checks.append((f"STAGING.STG_{table} unchanged", stg_rows == expected, f"expected {expected}, found {stg_rows}"))
        for table, expected in EXPECTED_CORE_COUNTS.items():
            core_rows = _scalar(cur, f"SELECT COUNT(*) FROM CORE.{table}")
            checks.append((f"CORE.{table} unchanged", core_rows == expected, f"expected {expected}, found {core_rows}"))
        for view, expected in EXPECTED_ANALYTICS_COUNTS.items():
            if expected is None:
                continue
            view_rows = _scalar(cur, f"SELECT COUNT(*) FROM ANALYTICS.{view}")
            checks.append((f"ANALYTICS.{view} unchanged", view_rows == expected, f"expected {expected}, found {view_rows}"))
    finally:
        conn.close()

    def _fmt(v, nd=3):
        return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "n/a"

    print("\nCustomer Risk Model")
    c = model_summaries.get("customer", {})
    print(f"Algorithm: {c.get('algorithm')}")
    print(f"ROC-AUC: {_fmt(c.get('roc_auc'))}")
    print(f"F1: {_fmt(c.get('f1'))}")
    print("PASS" if all(p for n, p, _ in checks if "Customer risk" in n or n == "ML_CUSTOMER_RISK exists") else "FAIL")

    print("\nProject Risk Model")
    p = model_summaries.get("project", {})
    print(f"Algorithm: {p.get('algorithm')}")
    print(f"ROC-AUC: {_fmt(p.get('roc_auc'))}")
    print(f"F1: {_fmt(p.get('f1'))}")
    print("PASS" if all(passed for name, passed, _ in checks if "Project risk" in name or name == "ML_PROJECT_RISK exists") else "FAIL")

    print("\nPayment Delay Model")
    pay = model_summaries.get("payment", {})
    print(f"Algorithm: {pay.get('algorithm')}")
    print(f"ROC-AUC: {_fmt(pay.get('roc_auc'))}")
    print(f"F1: {_fmt(pay.get('f1'))}")
    print("PASS" if all(passed for name, passed, _ in checks if "Payment delay" in name or name == "ML_PAYMENT_DELAY exists") else "FAIL")

    print("\nRevenue Forecast")
    r = model_summaries.get("revenue", {})
    print(f"Algorithm: {r.get('method')}")
    print(f"MAE: {_fmt(r.get('mae'), 0)}")
    print(f"RMSE: {_fmt(r.get('rmse'), 0)}")
    print("PASS" if all(passed for name, passed, _ in checks if "Revenue forecast" in name or name == "ML_REVENUE_FORECAST exists") else "FAIL")

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

    return failed_count == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
