"""Validates the Phase 2B RAW -> STAGING transformation. Run as:

    python -m etl.validate_staging

Per STAGING table: existence, RAW vs STAGING row counts, and VALID /
WARNING / INVALID counts (printed in the requested report format). Also
checks, across all tables: no duplicate primary keys among VALID records,
mandatory IDs non-null, numeric ranges and date fields sane, only the three
supported _data_quality_status values are present, FK-compatible IDs across
STAGING remain resolvable, and RAW itself was not modified by this layer.
"""

import sys

from etl.snowflake_connection import STAGING_TABLES, get_connection
from validation.validate_schema import MANDATORY_FIELDS, RANGE_CONSTRAINTS
from validation.validate_schema import PRIMARY_KEYS as RAW_PRIMARY_KEYS

# Phase 2A RAW row counts, captured at the end of the validated full load
# (201,777 total records, 60/60 checks passed). STAGING only ever reads RAW,
# so these counts must still match exactly whenever this validator runs --
# any drift means something outside this pipeline touched RAW.
EXPECTED_RAW_ROW_COUNTS = {
    "CUSTOMERS": 5000,
    "EMPLOYEES": 1000,
    "LEADS": 15000,
    "DEALS": 20000,
    "SUBSCRIPTIONS": 10000,
    "PROJECTS": 8000,
    "INVOICES": 30000,
    "PAYMENTS": 22777,
    "SUPPORT_TICKETS": 40000,
    "CUSTOMER_ACTIVITY": 50000,
}

VALID_DQ_STATUSES = {"VALID", "WARNING", "INVALID"}
MIN_PLAUSIBLE_DATE = "2000-01-01"
MAX_PLAUSIBLE_DATE = "2035-12-31"

# STAGING table -> the Phase 1 validate_schema.py key for that dataset, so
# mandatory-field and numeric-range rules are reused verbatim instead of
# being redefined (and risking drift) here.
PHASE1_KEY = {
    "STG_CUSTOMERS": "customers", "STG_EMPLOYEES": "employees", "STG_LEADS": "leads",
    "STG_DEALS": "deals", "STG_SUBSCRIPTIONS": "subscriptions", "STG_PROJECTS": "projects",
    "STG_INVOICES": "invoices", "STG_PAYMENTS": "payments",
    "STG_SUPPORT_TICKETS": "support_tickets", "STG_CUSTOMER_ACTIVITY": "customer_activity",
}

DATE_COLUMNS = {
    "STG_CUSTOMERS": ["signup_date", "contract_start_date", "renewal_date"],
    "STG_EMPLOYEES": ["hire_date"],
    "STG_LEADS": ["created_date", "converted_date"],
    "STG_DEALS": ["created_date", "close_date"],
    "STG_SUBSCRIPTIONS": ["start_date", "end_date"],
    "STG_PROJECTS": ["start_date", "planned_end_date", "actual_end_date"],
    "STG_INVOICES": ["invoice_date", "due_date"],
    "STG_PAYMENTS": ["payment_date"],
    "STG_SUPPORT_TICKETS": ["created_date", "resolution_date"],
    "STG_CUSTOMER_ACTIVITY": ["activity_date"],
}

# child table, child FK column, parent table, parent PK column -- the same
# relationships Phase 1 validates in validation/validate_relationships.py,
# re-checked here against the cleaned STAGING IDs.
STAGING_FOREIGN_KEYS = [
    ("STG_LEADS", "customer_id", "STG_CUSTOMERS", "customer_id"),
    ("STG_LEADS", "assigned_salesperson_id", "STG_EMPLOYEES", "employee_id"),
    ("STG_DEALS", "customer_id", "STG_CUSTOMERS", "customer_id"),
    ("STG_DEALS", "sales_rep_id", "STG_EMPLOYEES", "employee_id"),
    ("STG_SUBSCRIPTIONS", "customer_id", "STG_CUSTOMERS", "customer_id"),
    ("STG_PROJECTS", "customer_id", "STG_CUSTOMERS", "customer_id"),
    ("STG_PROJECTS", "project_manager_id", "STG_EMPLOYEES", "employee_id"),
    ("STG_INVOICES", "customer_id", "STG_CUSTOMERS", "customer_id"),
    ("STG_PAYMENTS", "invoice_id", "STG_INVOICES", "invoice_id"),
    ("STG_PAYMENTS", "customer_id", "STG_CUSTOMERS", "customer_id"),
    ("STG_SUPPORT_TICKETS", "customer_id", "STG_CUSTOMERS", "customer_id"),
    ("STG_SUPPORT_TICKETS", "agent_id", "STG_EMPLOYEES", "employee_id"),
    ("STG_CUSTOMER_ACTIVITY", "customer_id", "STG_CUSTOMERS", "customer_id"),
]


def _table_exists(cur, schema, table):
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (schema, table),
    )
    return cur.fetchone()[0] == 1


def _row_count(cur, schema, table):
    cur.execute(f"SELECT COUNT(*) FROM NEXORA_DB.{schema}.{table}")
    return cur.fetchone()[0]


def _dq_counts(cur, table):
    cur.execute(f"SELECT _data_quality_status, COUNT(*) FROM NEXORA_DB.STAGING.{table} GROUP BY _data_quality_status")
    counts = {"VALID": 0, "WARNING": 0, "INVALID": 0}
    unexpected = []
    for status, cnt in cur.fetchall():
        if status in counts:
            counts[status] = cnt
        else:
            unexpected.append((status, cnt))
    return counts, unexpected


def _duplicate_pk_count_valid(cur, table, pk):
    cur.execute(
        f"SELECT COUNT(*) FROM ("
        f"  SELECT {pk} FROM NEXORA_DB.STAGING.{table} WHERE _data_quality_status = 'VALID'"
        f"  GROUP BY {pk} HAVING COUNT(*) > 1"
        f")"
    )
    return cur.fetchone()[0]


def _null_count(cur, table, field):
    cur.execute(f"SELECT COUNT(*) FROM NEXORA_DB.STAGING.{table} WHERE {field} IS NULL")
    return cur.fetchone()[0]


def _range_violation_count(cur, table, column, low, high):
    cur.execute(
        f"SELECT COUNT(*) FROM NEXORA_DB.STAGING.{table} "
        f"WHERE {column} IS NOT NULL AND ({column} < {low} OR {column} > {high})"
    )
    return cur.fetchone()[0]


def _date_sanity_violation_count(cur, table, column):
    cur.execute(
        f"SELECT COUNT(*) FROM NEXORA_DB.STAGING.{table} WHERE {column} IS NOT NULL "
        f"AND ({column} < '{MIN_PLAUSIBLE_DATE}' OR {column} > '{MAX_PLAUSIBLE_DATE}')"
    )
    return cur.fetchone()[0]


def _fk_orphan_count(cur, child, child_col, parent, parent_col):
    cur.execute(
        f"SELECT COUNT(*) FROM NEXORA_DB.STAGING.{child} c WHERE c.{child_col} IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM NEXORA_DB.STAGING.{parent} p WHERE p.{parent_col} = c.{child_col})"
    )
    return cur.fetchone()[0]


def run():
    conn = get_connection()
    extra_checks = []
    table_pass = {}
    dq_totals = {"VALID": 0, "WARNING": 0, "INVALID": 0}

    print("NEXORA STAGING DATA QUALITY VALIDATION")

    try:
        cur = conn.cursor()

        for stg_table, raw_table in STAGING_TABLES:
            print(f"\n{stg_table}")

            raw_exists = _table_exists(cur, "RAW", raw_table)
            stg_exists = _table_exists(cur, "STAGING", stg_table)
            if not stg_exists:
                print("  STAGING table not found")
                table_pass[stg_table] = False
                extra_checks.append((f"{stg_table} exists", False, "TABLE NOT FOUND"))
                continue
            extra_checks.append((f"{stg_table} exists", True, "table found"))

            raw_rows = _row_count(cur, "RAW", raw_table) if raw_exists else -1
            staged_rows = _row_count(cur, "STAGING", stg_table)
            print(f"RAW rows: {raw_rows}")
            print(f"STAGING rows: {staged_rows}")

            dq_counts, unexpected_statuses = _dq_counts(cur, stg_table)
            print(f"VALID: {dq_counts['VALID']}")
            print(f"WARNING: {dq_counts['WARNING']}")
            print(f"INVALID: {dq_counts['INVALID']}")
            for k in dq_totals:
                dq_totals[k] += dq_counts[k]

            # Full-refresh STAGING dedupes on primary key (see
            # docs/staging_data_quality.md), so STAGING <= RAW is the
            # "explainable" relationship -- equality is expected here since
            # Phase 1/2A already validated zero primary-key duplicates in RAW.
            row_counts_explainable = raw_exists and staged_rows <= raw_rows
            status_ok = not unexpected_statuses

            pk = RAW_PRIMARY_KEYS[PHASE1_KEY[stg_table]]
            dupes = _duplicate_pk_count_valid(cur, stg_table, pk)

            null_detail = {f: _null_count(cur, stg_table, f) for f in MANDATORY_FIELDS[PHASE1_KEY[stg_table]]}
            null_total = sum(null_detail.values())

            range_violations = {}
            for column, low, high in RANGE_CONSTRAINTS.get(PHASE1_KEY[stg_table], []):
                v = _range_violation_count(cur, stg_table, column, low, high)
                if v:
                    range_violations[column] = v

            date_violations = {}
            for column in DATE_COLUMNS.get(stg_table, []):
                v = _date_sanity_violation_count(cur, stg_table, column)
                if v:
                    date_violations[column] = v

            table_ok = (
                row_counts_explainable and status_ok and dupes == 0
                and null_total == 0 and not range_violations and not date_violations
            )
            table_pass[stg_table] = table_ok
            print("PASS" if table_ok else "FAIL")

            extra_checks.append((f"{stg_table} row counts explainable (RAW vs STAGING)", row_counts_explainable,
                                  f"RAW={raw_rows} STAGING={staged_rows}"))
            extra_checks.append((f"{stg_table} _data_quality_status values supported", status_ok,
                                  "only VALID/WARNING/INVALID present" if status_ok else f"unexpected values: {unexpected_statuses}"))
            extra_checks.append((f"{stg_table} no duplicate {pk} among VALID rows", dupes == 0, f"{dupes} duplicate keys"))
            extra_checks.append((f"{stg_table} mandatory IDs non-null", null_total == 0,
                                  "no nulls" if null_total == 0 else f"nulls: {null_detail}"))
            extra_checks.append((f"{stg_table} numeric ranges valid", not range_violations,
                                  "within range" if not range_violations else f"violations: {range_violations}"))
            extra_checks.append((f"{stg_table} date fields valid", not date_violations,
                                  "all dates plausible" if not date_violations else f"violations: {date_violations}"))

        print("\nRAW immutability check (current RAW counts vs. the validated Phase 2A load):")
        for stg_table, raw_table in STAGING_TABLES:
            raw_rows = _row_count(cur, "RAW", raw_table)
            expected = EXPECTED_RAW_ROW_COUNTS[raw_table]
            unmodified = raw_rows == expected
            print(f"  RAW.{raw_table}: expected={expected} actual={raw_rows} {'PASS' if unmodified else 'FAIL'}")
            extra_checks.append((f"RAW.{raw_table} unmodified", unmodified, f"expected {expected}, found {raw_rows}"))

        print("\nForeign-key-compatible IDs across STAGING:")
        for child, ccol, parent, pcol in STAGING_FOREIGN_KEYS:
            orphans = _fk_orphan_count(cur, child, ccol, parent, pcol)
            ok = orphans == 0
            print(f"  {child}.{ccol} -> {parent}.{pcol}: {orphans} orphaned {'PASS' if ok else 'FAIL'}")
            extra_checks.append((f"{child}.{ccol} -> {parent}.{pcol}", ok, f"{orphans} orphaned"))
    finally:
        conn.close()

    tables_checked = len(STAGING_TABLES)
    tables_passed = sum(1 for ok in table_pass.values() if ok)
    tables_failed = tables_checked - tables_passed

    print("\n" + "=" * 60)
    print("Additional checks:")
    for name, passed, detail in extra_checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print("-" * 60)
    print(f"Tables checked: {tables_checked}")
    print(f"Passed: {tables_passed}")
    print(f"Failed: {tables_failed}")
    print("-" * 60)
    print(f"Total VALID rows: {dq_totals['VALID']}")
    print(f"Total WARNING rows: {dq_totals['WARNING']}")
    print(f"Total INVALID rows: {dq_totals['INVALID']}")
    print("=" * 60)

    all_extra_ok = all(p for _, p, _ in extra_checks)
    return tables_failed == 0 and all_extra_ok


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
