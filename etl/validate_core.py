"""Validates the Phase 2C STAGING -> CORE dimensional load. Run as:

    python -m etl.validate_core

Checks: all 6 dimensions and 8 facts exist; surrogate keys unique; business
keys present; DIM_DATE covers every date_key used by a fact; fact foreign
surrogate keys resolve; no duplicate fact business IDs; UNKNOWN member usage
(split into genuine unresolved lookups vs. a legitimately-NULL source
value); key numeric measures reconcile against STAGING; fact row counts
reconcile with eligible STAGING rows; INVALID STAGING rows never reach
CORE; SCD2 current-row uniqueness and effective_from/effective_to validity
for DIM_CUSTOMER/DIM_EMPLOYEE; and that RAW/STAGING were not modified.
"""

import sys

from etl.snowflake_connection import get_connection

DIMENSIONS = ["DIM_DATE", "DIM_REGION", "DIM_DEPARTMENT", "DIM_SERVICE", "DIM_CUSTOMER", "DIM_EMPLOYEE"]
FACTS = [
    "FACT_LEADS", "FACT_DEALS", "FACT_SUBSCRIPTIONS", "FACT_PROJECTS",
    "FACT_INVOICES", "FACT_PAYMENTS", "FACT_SUPPORT", "FACT_CUSTOMER_ACTIVITY",
]

DIM_SURROGATE_KEY = {
    "DIM_DATE": "date_key", "DIM_REGION": "region_key", "DIM_DEPARTMENT": "department_key",
    "DIM_SERVICE": "service_key", "DIM_CUSTOMER": "customer_key", "DIM_EMPLOYEE": "employee_key",
}
DIM_BUSINESS_KEY = {
    "DIM_REGION": "region_name", "DIM_DEPARTMENT": "department_name", "DIM_SERVICE": "service_name",
    "DIM_CUSTOMER": "customer_id", "DIM_EMPLOYEE": "employee_id",
}
SCD2_DIMS = {"DIM_CUSTOMER": "customer_id", "DIM_EMPLOYEE": "employee_id"}

FACT_BUSINESS_KEY = {
    "FACT_LEADS": "lead_id", "FACT_DEALS": "deal_id", "FACT_SUBSCRIPTIONS": "subscription_id",
    "FACT_PROJECTS": "project_id", "FACT_INVOICES": "invoice_id", "FACT_PAYMENTS": "payment_id",
    "FACT_SUPPORT": "ticket_id", "FACT_CUSTOMER_ACTIVITY": "activity_id",
}
FACT_STAGING_SOURCE = {
    "FACT_LEADS": "STG_LEADS", "FACT_DEALS": "STG_DEALS", "FACT_SUBSCRIPTIONS": "STG_SUBSCRIPTIONS",
    "FACT_PROJECTS": "STG_PROJECTS", "FACT_INVOICES": "STG_INVOICES", "FACT_PAYMENTS": "STG_PAYMENTS",
    "FACT_SUPPORT": "STG_SUPPORT_TICKETS", "FACT_CUSTOMER_ACTIVITY": "STG_CUSTOMER_ACTIVITY",
}
# one representative, directly-comparable numeric measure per fact (copied
# verbatim from STAGING, not a derived one) for check #9
FACT_MEASURE_CHECK = {
    "FACT_LEADS": "lead_score", "FACT_DEALS": "deal_value", "FACT_SUBSCRIPTIONS": "mrr",
    "FACT_PROJECTS": "budget", "FACT_INVOICES": "total_amount", "FACT_PAYMENTS": "amount_paid",
    "FACT_SUPPORT": "resolution_time_hours", "FACT_CUSTOMER_ACTIVITY": "engagement_points",
}

# (fact table, fact surrogate-key column, dimension it should resolve
# against, STAGING table + column that surrogate key was derived from) --
# drives checks #5, #6, and #8.
FACT_DIM_LOOKUPS = [
    ("FACT_LEADS", "customer_key", "DIM_CUSTOMER", "STG_LEADS", "customer_id"),
    ("FACT_LEADS", "salesperson_employee_key", "DIM_EMPLOYEE", "STG_LEADS", "assigned_salesperson_id"),
    ("FACT_LEADS", "created_date_key", "DIM_DATE", "STG_LEADS", "created_date"),
    ("FACT_LEADS", "converted_date_key", "DIM_DATE", "STG_LEADS", "converted_date"),
    ("FACT_DEALS", "customer_key", "DIM_CUSTOMER", "STG_DEALS", "customer_id"),
    ("FACT_DEALS", "sales_rep_employee_key", "DIM_EMPLOYEE", "STG_DEALS", "sales_rep_id"),
    ("FACT_DEALS", "service_key", "DIM_SERVICE", "STG_DEALS", "product"),
    ("FACT_DEALS", "region_key", "DIM_REGION", "STG_DEALS", "region"),
    ("FACT_DEALS", "created_date_key", "DIM_DATE", "STG_DEALS", "created_date"),
    ("FACT_DEALS", "close_date_key", "DIM_DATE", "STG_DEALS", "close_date"),
    ("FACT_SUBSCRIPTIONS", "customer_key", "DIM_CUSTOMER", "STG_SUBSCRIPTIONS", "customer_id"),
    ("FACT_SUBSCRIPTIONS", "service_key", "DIM_SERVICE", "STG_SUBSCRIPTIONS", "plan"),
    ("FACT_SUBSCRIPTIONS", "start_date_key", "DIM_DATE", "STG_SUBSCRIPTIONS", "start_date"),
    ("FACT_SUBSCRIPTIONS", "end_date_key", "DIM_DATE", "STG_SUBSCRIPTIONS", "end_date"),
    ("FACT_PROJECTS", "customer_key", "DIM_CUSTOMER", "STG_PROJECTS", "customer_id"),
    ("FACT_PROJECTS", "project_manager_employee_key", "DIM_EMPLOYEE", "STG_PROJECTS", "project_manager_id"),
    ("FACT_PROJECTS", "service_key", "DIM_SERVICE", "STG_PROJECTS", "project_type"),
    ("FACT_PROJECTS", "start_date_key", "DIM_DATE", "STG_PROJECTS", "start_date"),
    ("FACT_PROJECTS", "planned_end_date_key", "DIM_DATE", "STG_PROJECTS", "planned_end_date"),
    ("FACT_PROJECTS", "actual_end_date_key", "DIM_DATE", "STG_PROJECTS", "actual_end_date"),
    ("FACT_INVOICES", "customer_key", "DIM_CUSTOMER", "STG_INVOICES", "customer_id"),
    ("FACT_INVOICES", "invoice_date_key", "DIM_DATE", "STG_INVOICES", "invoice_date"),
    ("FACT_INVOICES", "due_date_key", "DIM_DATE", "STG_INVOICES", "due_date"),
    ("FACT_PAYMENTS", "customer_key", "DIM_CUSTOMER", "STG_PAYMENTS", "customer_id"),
    ("FACT_PAYMENTS", "payment_date_key", "DIM_DATE", "STG_PAYMENTS", "payment_date"),
    ("FACT_SUPPORT", "customer_key", "DIM_CUSTOMER", "STG_SUPPORT_TICKETS", "customer_id"),
    ("FACT_SUPPORT", "agent_employee_key", "DIM_EMPLOYEE", "STG_SUPPORT_TICKETS", "agent_id"),
    ("FACT_SUPPORT", "created_date_key", "DIM_DATE", "STG_SUPPORT_TICKETS", "created_date"),
    ("FACT_SUPPORT", "resolution_date_key", "DIM_DATE", "STG_SUPPORT_TICKETS", "resolution_date"),
    ("FACT_CUSTOMER_ACTIVITY", "customer_key", "DIM_CUSTOMER", "STG_CUSTOMER_ACTIVITY", "customer_id"),
    ("FACT_CUSTOMER_ACTIVITY", "activity_date_key", "DIM_DATE", "STG_CUSTOMER_ACTIVITY", "activity_date"),
]

# Phase 2A/2B baseline row counts (RAW and STAGING are 1:1 in this dataset --
# STAGING's dedup found zero primary-key duplicates in RAW). Any drift here
# means something outside Phase 2C touched RAW or STAGING.
EXPECTED_ROW_COUNTS = {
    "CUSTOMERS": 5000, "EMPLOYEES": 1000, "LEADS": 15000, "DEALS": 20000,
    "SUBSCRIPTIONS": 10000, "PROJECTS": 8000, "INVOICES": 30000, "PAYMENTS": 22777,
    "SUPPORT_TICKETS": 40000, "CUSTOMER_ACTIVITY": 50000,
}


def _exists(cur, schema, table):
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (schema, table),
    )
    return cur.fetchone()[0] == 1


def _scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def run():
    conn = get_connection()
    checks = []          # (name, passed, detail) -- printed as the flat [PASS]/[FAIL] list
    dim_status = {}       # name -> PASS/FAIL, for the requested summary block
    fact_status = {}
    total_unresolved = 0
    total_unknown_benign = 0
    total_dup_fact_ids = 0
    total_scd_violations = 0

    print("NEXORA CORE DATA WAREHOUSE VALIDATION")
    print(f"\nDimensions checked: {len(DIMENSIONS)}")
    print(f"Facts checked: {len(FACTS)}")

    try:
        cur = conn.cursor()

        # ---- 1. dimensions exist; 3. surrogate keys unique; 4. business keys present ----
        for dim in DIMENSIONS:
            exists = _exists(cur, "CORE", dim)
            if not exists:
                checks.append((f"{dim} exists", False, "TABLE NOT FOUND"))
                dim_status[dim] = "FAIL"
                continue
            checks.append((f"{dim} exists", True, "table found"))

            pk = DIM_SURROGATE_KEY[dim]
            dupe_keys = _scalar(cur, f"SELECT COUNT(*) FROM (SELECT {pk} FROM CORE.{dim} GROUP BY {pk} HAVING COUNT(*) > 1)")
            keys_ok = dupe_keys == 0
            checks.append((f"{dim} surrogate key {pk} unique", keys_ok, f"{dupe_keys} duplicate surrogate keys"))

            bk_ok, bk_detail = True, "n/a (DIM_DATE has no single business key)"
            if dim in DIM_BUSINESS_KEY:
                bk = DIM_BUSINESS_KEY[dim]
                nulls = _scalar(cur, f"SELECT COUNT(*) FROM CORE.{dim} WHERE {bk} IS NULL AND {pk} <> -1")
                bk_ok = nulls == 0
                bk_detail = f"{nulls} rows missing {bk}"
            checks.append((f"{dim} business key present", bk_ok, bk_detail))

            dim_status[dim] = "PASS" if (exists and keys_ok and bk_ok) else "FAIL"

        # ---- 12/13. SCD2 current-row uniqueness + effective date validity ----
        for dim, bk in SCD2_DIMS.items():
            multi_current = _scalar(cur, f"""
                SELECT COUNT(*) FROM (
                    SELECT {bk} FROM CORE.{dim} WHERE {bk} <> '-1'
                    GROUP BY {bk} HAVING SUM(IFF(is_current, 1, 0)) > 1
                )
            """)
            checks.append((f"{dim} exactly one is_current per {bk}", multi_current == 0, f"{multi_current} business keys with >1 current row"))
            total_scd_violations += multi_current

            bad_current = _scalar(cur, f"SELECT COUNT(*) FROM CORE.{dim} WHERE is_current = TRUE AND effective_to IS NOT NULL")
            bad_expired = _scalar(cur, f"SELECT COUNT(*) FROM CORE.{dim} WHERE is_current = FALSE AND (effective_to IS NULL OR effective_to < effective_from)")
            range_ok = bad_current == 0 and bad_expired == 0
            checks.append((f"{dim} effective_from/effective_to ranges valid", range_ok,
                            f"{bad_current} current rows with effective_to set, {bad_expired} expired rows with missing/invalid effective_to"))
            total_scd_violations += bad_current + bad_expired

        # ---- 2. facts exist; 7. no duplicate business IDs; 10. row counts reconcile;
        #      11. INVALID staging rows absent; 9. measures reconcile ----
        for fact in FACTS:
            exists = _exists(cur, "CORE", fact)
            if not exists:
                checks.append((f"{fact} exists", False, "TABLE NOT FOUND"))
                fact_status[fact] = "FAIL"
                continue
            checks.append((f"{fact} exists", True, "table found"))

            bk = FACT_BUSINESS_KEY[fact]
            stg = FACT_STAGING_SOURCE[fact]

            dupes = _scalar(cur, f"SELECT COUNT(*) FROM (SELECT {bk} FROM CORE.{fact} GROUP BY {bk} HAVING COUNT(*) > 1)")
            dupes_ok = dupes == 0
            checks.append((f"{fact} no duplicate {bk}", dupes_ok, f"{dupes} duplicate business IDs"))
            total_dup_fact_ids += dupes

            fact_rows = _scalar(cur, f"SELECT COUNT(*) FROM CORE.{fact}")
            eligible_rows = _scalar(cur, f"SELECT COUNT(*) FROM STAGING.{stg} WHERE _data_quality_status IN ('VALID','WARNING')")
            counts_ok = fact_rows == eligible_rows
            checks.append((f"{fact} row count reconciles with eligible STAGING", counts_ok,
                            f"CORE={fact_rows} STAGING(VALID+WARNING)={eligible_rows}"))

            invalid_leaked = _scalar(cur, f"""
                SELECT COUNT(*) FROM CORE.{fact} f
                JOIN STAGING.{stg} s ON s.{bk} = f.{bk}
                WHERE s._data_quality_status = 'INVALID'
            """)
            invalid_ok = invalid_leaked == 0
            checks.append((f"{fact} contains no INVALID STAGING rows", invalid_ok, f"{invalid_leaked} leaked"))

            measure = FACT_MEASURE_CHECK[fact]
            fact_sum = _scalar(cur, f"SELECT SUM({measure}) FROM CORE.{fact}") or 0
            stg_sum = _scalar(cur, f"SELECT SUM({measure}) FROM STAGING.{stg} WHERE _data_quality_status IN ('VALID','WARNING')") or 0
            measure_ok = abs(float(fact_sum) - float(stg_sum)) < 0.01
            checks.append((f"{fact}.{measure} sum matches STAGING", measure_ok, f"CORE={fact_sum} STAGING={stg_sum}"))

            fact_status[fact] = "PASS" if (exists and dupes_ok and counts_ok and invalid_ok and measure_ok) else "FAIL"

        # ---- 5/6/8. DIM_DATE coverage, FK resolution, UNKNOWN usage ----
        for fact, col, dim, stg, src_col in FACT_DIM_LOOKUPS:
            bk = FACT_BUSINESS_KEY[fact]
            pk = DIM_SURROGATE_KEY[dim]

            orphans = _scalar(cur, f"""
                SELECT COUNT(*) FROM CORE.{fact} f
                WHERE NOT EXISTS (SELECT 1 FROM CORE.{dim} d WHERE d.{pk} = f.{col})
            """)
            check_label = f"{fact}.{col} resolves against {dim}" if dim != "DIM_DATE" else f"{fact}.{col} covered by DIM_DATE"
            checks.append((check_label, orphans == 0, f"{orphans} unresolved surrogate key values"))

            benign, unresolved = _scalar_pair(cur, f"""
                SELECT
                    COALESCE(COUNT_IF(s.{src_col} IS NULL), 0) AS benign_null_source,
                    COALESCE(COUNT_IF(s.{src_col} IS NOT NULL), 0) AS unresolved_with_source_value
                FROM CORE.{fact} f
                JOIN STAGING.{stg} s ON s.{bk} = f.{bk}
                WHERE f.{col} = -1
            """)
            total_unknown_benign += benign
            total_unresolved += unresolved
            if unresolved:
                checks.append((f"{fact}.{col} unresolved lookups (source had a value)", False, f"{unresolved} rows"))

        # ---- 14. RAW / STAGING unchanged ----
        for table, expected in EXPECTED_ROW_COUNTS.items():
            raw_rows = _scalar(cur, f"SELECT COUNT(*) FROM RAW.{table}")
            stg_rows = _scalar(cur, f"SELECT COUNT(*) FROM STAGING.STG_{table}")
            raw_ok = raw_rows == expected
            stg_ok = stg_rows == expected
            checks.append((f"RAW.{table} unchanged", raw_ok, f"expected {expected}, found {raw_rows}"))
            checks.append((f"STAGING.STG_{table} unchanged", stg_ok, f"expected {expected}, found {stg_rows}"))
    finally:
        conn.close()

    print("\nDimension results:")
    for dim in DIMENSIONS:
        print(f"{dim:<15s} {dim_status.get(dim, 'FAIL')}")

    print("\nFact results:")
    for fact in FACTS:
        print(f"{fact:<24s} {fact_status.get(fact, 'FAIL')}")

    print(f"\nUnresolved dimension lookups: {total_unresolved}")
    print(f"(benign -- source had no value to look up: {total_unknown_benign})")
    print(f"Duplicate fact business IDs: {total_dup_fact_ids}")
    print(f"SCD current-row violations: {total_scd_violations}")

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

    all_dims_ok = all(v == "PASS" for v in dim_status.values())
    all_facts_ok = all(v == "PASS" for v in fact_status.values())
    return failed_count == 0 and all_dims_ok and all_facts_ok


def _scalar_pair(cur, sql):
    cur.execute(sql)
    row = cur.fetchone()
    return row[0], row[1]


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
