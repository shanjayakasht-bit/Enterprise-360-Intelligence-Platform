"""Validates the Phase 2D ANALYTICS layer. Run as:

    python -m etl.validate_analytics

Checks: all 10 views exist and execute; executive KPIs aren't unexpectedly
null; VW_CUSTOMER_360 has exactly one row per customer; revenue aggregates
don't exceed explainable source totals; no customer duplication in
customer-level views; VW_FINANCE_SUMMARY doesn't double count invoice/
payment amounts; VW_AT_RISK_CUSTOMERS ranking is deterministic; region and
service totals reconcile against the overall total; the view SQL contains
no DML against CORE; and RAW/STAGING/CORE remain unchanged.
"""

import sys
from pathlib import Path

from etl.snowflake_connection import get_connection

ROOT_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT_DIR / "snowflake" / "sql"
VIEW_SQL_FILES = [SQL_DIR / "09_analytics_views.sql", SQL_DIR / "10_analytics_kpis.sql"]

VIEWS = [
    "VW_EXECUTIVE_OVERVIEW", "VW_CUSTOMER_360", "VW_REVENUE_TRENDS", "VW_CUSTOMER_HEALTH",
    "VW_PROJECT_RISK", "VW_SUPPORT_HEALTH", "VW_FINANCE_SUMMARY", "VW_REGION_PERFORMANCE",
    "VW_SERVICE_PERFORMANCE", "VW_AT_RISK_CUSTOMERS",
]

# Columns on VW_EXECUTIVE_OVERVIEW expected to always be populated for this
# (fully populated) dataset -- a NULL here would be a real regression, not
# a legitimate "no data yet" case.
EXECUTIVE_KPI_COLUMNS = [
    "TOTAL_REVENUE", "ACTIVE_CUSTOMERS", "ACTIVE_SUBSCRIPTIONS", "ACTIVE_PROJECTS",
    "PROJECTS_AT_RISK", "OPEN_SUPPORT_TICKETS", "SUPPORT_SLA_PERCENTAGE",
    "AVERAGE_CUSTOMER_HEALTH", "TOTAL_INVOICE_AMOUNT", "TOTAL_PAYMENTS_RECEIVED",
    "OUTSTANDING_AMOUNT", "ENTERPRISE_HEALTH_SCORE",
]

CUSTOMER_LEVEL_VIEWS = ["VW_CUSTOMER_360", "VW_CUSTOMER_HEALTH", "VW_AT_RISK_CUSTOMERS"]

# Phase 2A/2B/2C baseline row counts. Any drift means something outside
# Phase 2D touched RAW, STAGING, or CORE -- ANALYTICS views are read-only.
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

FORBIDDEN_DML = ["INSERT INTO CORE", "UPDATE CORE", "DELETE FROM CORE", "MERGE INTO CORE", "TRUNCATE TABLE CORE"]


def _scalar(cur, sql, params=None):
    cur.execute(sql, params) if params else cur.execute(sql)
    return cur.fetchone()[0]


def _view_exists(cur, view):
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA = 'ANALYTICS' AND TABLE_NAME = %s",
        (view,),
    )
    return cur.fetchone()[0] == 1


def run():
    conn = get_connection()
    checks = []
    view_status = {}
    kpi_sample = {}

    print("NEXORA ANALYTICS VALIDATION")
    print(f"\nViews checked: {len(VIEWS)}")

    try:
        cur = conn.cursor()

        # ---- 1/2. views exist and execute ----
        for view in VIEWS:
            exists = _view_exists(cur, view)
            if not exists:
                checks.append((f"{view} exists", False, "VIEW NOT FOUND"))
                view_status[view] = "FAIL"
                continue
            checks.append((f"{view} exists", True, "view found"))
            try:
                cur.execute(f"SELECT COUNT(*) FROM ANALYTICS.{view}")
                rows = cur.fetchone()[0]
                checks.append((f"{view} executes successfully", True, f"{rows} rows"))
                view_status[view] = "PASS"
            except Exception as exc:
                checks.append((f"{view} executes successfully", False, str(exc)))
                view_status[view] = "FAIL"

        # ---- 3. executive KPIs not unexpectedly null ----
        cur.execute(f"SELECT {', '.join(EXECUTIVE_KPI_COLUMNS)} FROM ANALYTICS.VW_EXECUTIVE_OVERVIEW")
        row = cur.fetchone()
        kpi_row = dict(zip(EXECUTIVE_KPI_COLUMNS, row)) if row else {}
        null_kpis = [c for c in EXECUTIVE_KPI_COLUMNS if kpi_row.get(c) is None]
        checks.append(("VW_EXECUTIVE_OVERVIEW KPIs not unexpectedly null", not null_kpis,
                        "all populated" if not null_kpis else f"NULL: {null_kpis}"))
        kpi_sample = kpi_row

        # ---- 4. VW_CUSTOMER_360 one row per customer; 6. no dup in customer-level views ----
        for view in CUSTOMER_LEVEL_VIEWS:
            total = _scalar(cur, f"SELECT COUNT(*) FROM ANALYTICS.{view}")
            distinct = _scalar(cur, f"SELECT COUNT(DISTINCT customer_id) FROM ANALYTICS.{view}")
            ok = total == distinct
            checks.append((f"{view} no customer duplication", ok, f"rows={total} distinct_customer_id={distinct}"))
        dim_customer_current = _scalar(cur, "SELECT COUNT(*) FROM CORE.DIM_CUSTOMER WHERE is_current = TRUE AND customer_key <> -1")
        customer_360_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.VW_CUSTOMER_360")
        checks.append(("VW_CUSTOMER_360 one row per current customer", customer_360_rows == dim_customer_current,
                        f"VW_CUSTOMER_360={customer_360_rows} current DIM_CUSTOMER={dim_customer_current}"))

        # ---- 5. revenue aggregates do not exceed explainable source totals ----
        total_revenue = _scalar(cur, "SELECT SUM(IFF(is_won, net_deal_value, 0)) FROM CORE.FACT_DEALS")
        total_pipeline = _scalar(cur, "SELECT SUM(deal_value) FROM CORE.FACT_DEALS")
        revenue_within_pipeline = total_revenue <= total_pipeline
        checks.append(("total_revenue does not exceed total deal pipeline value", revenue_within_pipeline,
                        f"total_revenue={total_revenue} total_pipeline_value={total_pipeline}"))

        total_invoiced = _scalar(cur, "SELECT SUM(total_amount) FROM CORE.FACT_INVOICES")
        total_collected = _scalar(cur, "SELECT SUM(amount_paid) FROM CORE.FACT_PAYMENTS")
        payments_within_invoiced = total_collected <= total_invoiced
        checks.append(("total_payments_received does not exceed total_invoice_amount", payments_within_invoiced,
                        f"collected={total_collected} invoiced={total_invoiced}"))

        # ---- 7. VW_FINANCE_SUMMARY does not double count ----
        vw_invoice_sum = _scalar(cur, "SELECT SUM(total_amount) FROM ANALYTICS.VW_FINANCE_SUMMARY")
        vw_payments_sum = _scalar(cur, "SELECT SUM(payments_received) FROM ANALYTICS.VW_FINANCE_SUMMARY")
        invoice_match = abs(float(vw_invoice_sum) - float(total_invoiced)) < 0.01
        payments_match = abs(float(vw_payments_sum) - float(total_collected)) < 0.01
        checks.append(("VW_FINANCE_SUMMARY invoice total matches CORE.FACT_INVOICES (no fan-out)", invoice_match,
                        f"view={vw_invoice_sum} core={total_invoiced}"))
        checks.append(("VW_FINANCE_SUMMARY payments total matches CORE.FACT_PAYMENTS (no fan-out)", payments_match,
                        f"view={vw_payments_sum} core={total_collected}"))
        vw_finance_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.VW_FINANCE_SUMMARY")
        core_invoice_rows = _scalar(cur, "SELECT COUNT(*) FROM CORE.FACT_INVOICES")
        checks.append(("VW_FINANCE_SUMMARY grain is one row per invoice (no fan-out)", vw_finance_rows == core_invoice_rows,
                        f"view_rows={vw_finance_rows} FACT_INVOICES_rows={core_invoice_rows}"))

        # ---- 8. at-risk ranking deterministic ----
        cur.execute("SELECT customer_id FROM ANALYTICS.VW_AT_RISK_CUSTOMERS ORDER BY risk_rank")
        order_1 = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT customer_id FROM ANALYTICS.VW_AT_RISK_CUSTOMERS ORDER BY risk_rank")
        order_2 = [r[0] for r in cur.fetchall()]
        deterministic = order_1 == order_2 and len(order_1) > 0
        checks.append(("VW_AT_RISK_CUSTOMERS ranking is deterministic across reruns", deterministic,
                        f"{len(order_1)} customers, identical order both runs" if deterministic else "ORDER MISMATCH BETWEEN RUNS"))

        # ---- 9. region totals reconcile ----
        region_revenue_sum = _scalar(cur, "SELECT SUM(revenue) FROM ANALYTICS.VW_REGION_PERFORMANCE")
        region_ok = abs(float(region_revenue_sum) - float(total_revenue)) < 0.01
        checks.append(("VW_REGION_PERFORMANCE revenue reconciles with overall total_revenue", region_ok,
                        f"region_sum={region_revenue_sum} overall={total_revenue}"))

        # ---- 10. service totals reconcile ----
        service_revenue_sum = _scalar(cur, "SELECT SUM(revenue) FROM ANALYTICS.VW_SERVICE_PERFORMANCE")
        service_ok = abs(float(service_revenue_sum) - float(total_revenue)) < 0.01
        checks.append(("VW_SERVICE_PERFORMANCE revenue reconciles with overall total_revenue", service_ok,
                        f"service_sum={service_revenue_sum} overall={total_revenue}"))

        # ---- 11. analytics SQL contains no DML against CORE ----
        for path in VIEW_SQL_FILES:
            text = path.read_text(encoding="utf-8").upper()
            found = [kw for kw in FORBIDDEN_DML if kw in text]
            checks.append((f"{path.name} contains no DML against CORE", not found,
                            "none found" if not found else f"found: {found}"))

        # ---- 12. RAW / STAGING / CORE unchanged ----
        for table, expected in EXPECTED_RAW_STAGING_COUNTS.items():
            raw_rows = _scalar(cur, f"SELECT COUNT(*) FROM RAW.{table}")
            stg_rows = _scalar(cur, f"SELECT COUNT(*) FROM STAGING.STG_{table}")
            checks.append((f"RAW.{table} unchanged", raw_rows == expected, f"expected {expected}, found {raw_rows}"))
            checks.append((f"STAGING.STG_{table} unchanged", stg_rows == expected, f"expected {expected}, found {stg_rows}"))
        for table, expected in EXPECTED_CORE_COUNTS.items():
            core_rows = _scalar(cur, f"SELECT COUNT(*) FROM CORE.{table}")
            checks.append((f"CORE.{table} unchanged", core_rows == expected, f"expected {expected}, found {core_rows}"))
    finally:
        conn.close()

    print("\nView results:")
    for view in VIEWS:
        print(f"{view:<24s} {view_status.get(view, 'FAIL')}")

    print("\nSample KPI values:")
    print(f"Total Revenue: {kpi_sample.get('TOTAL_REVENUE')}")
    print(f"Active Customers: {kpi_sample.get('ACTIVE_CUSTOMERS')}")
    print(f"Projects at Risk: {kpi_sample.get('PROJECTS_AT_RISK')}")
    print(f"Support SLA: {kpi_sample.get('SUPPORT_SLA_PERCENTAGE')}")
    print(f"Enterprise Health Score: {kpi_sample.get('ENTERPRISE_HEALTH_SCORE')}")

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

    all_views_ok = all(v == "PASS" for v in view_status.values())
    return failed_count == 0 and all_views_ok


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
