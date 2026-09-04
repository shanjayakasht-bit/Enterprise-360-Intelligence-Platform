"""Validates the Snowflake RAW load against the local data/raw/ CSVs. Run as:

    python -m etl.validate_load

Checks, per table: row count match, no duplicate primary keys, no null
primary keys, and that the table exists -- plus a stage-contents check
across all ten datasets.
"""

import sys
from pathlib import Path

import pandas as pd

from etl.snowflake_connection import DATABASE, RAW_SCHEMA, RAW_TABLES, STAGE_NAME, get_connection

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data" / "raw"

PRIMARY_KEYS = {
    "CUSTOMERS": "customer_id",
    "EMPLOYEES": "employee_id",
    "LEADS": "lead_id",
    "DEALS": "deal_id",
    "SUBSCRIPTIONS": "subscription_id",
    "PROJECTS": "project_id",
    "INVOICES": "invoice_id",
    "PAYMENTS": "payment_id",
    "SUPPORT_TICKETS": "ticket_id",
    "CUSTOMER_ACTIVITY": "activity_id",
}


def _table_exists(cur, table):
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (RAW_SCHEMA, table),
    )
    return cur.fetchone()[0] == 1


def _stage_check(cur):
    cur.execute(f"LIST @{DATABASE}.{RAW_SCHEMA}.{STAGE_NAME}")
    staged = {Path(r[0]).name.removesuffix(".gz") for r in cur.fetchall()}
    expected = {filename for _, filename in RAW_TABLES}
    missing = expected - staged
    return missing


def _row_count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {DATABASE}.{RAW_SCHEMA}.{table}")
    return cur.fetchone()[0]


def _duplicate_pk_count(cur, table, pk):
    cur.execute(
        f"SELECT COUNT(*) FROM ("
        f"  SELECT {pk} FROM {DATABASE}.{RAW_SCHEMA}.{table} "
        f"  WHERE {pk} IS NOT NULL GROUP BY {pk} HAVING COUNT(*) > 1"
        f")"
    )
    return cur.fetchone()[0]


def _null_pk_count(cur, table, pk):
    cur.execute(f"SELECT COUNT(*) FROM {DATABASE}.{RAW_SCHEMA}.{table} WHERE {pk} IS NULL")
    return cur.fetchone()[0]


def run():
    conn = get_connection()
    checks = []
    try:
        cur = conn.cursor()

        missing_files = _stage_check(cur)
        stage_ok = not missing_files
        checks.append((
            "stage contains expected files", stage_ok,
            "all 10 files present in NEXORA_RAW_STAGE" if stage_ok else f"missing from stage: {sorted(missing_files)}",
        ))

        for table, filename in RAW_TABLES:
            print(f"\n{filename}")

            exists = _table_exists(cur, table)
            checks.append((f"{table} table exists", exists, "table found" if exists else "TABLE NOT FOUND"))
            if not exists:
                print("  Snowflake table not found - skipping remaining checks for this table")
                continue

            local_rows = len(pd.read_csv(DATA_DIR / filename))
            snowflake_rows = _row_count(cur, table)
            row_match = local_rows == snowflake_rows
            print(f"  Local rows: {local_rows}")
            print(f"  Snowflake rows: {snowflake_rows}")
            print("  PASS" if row_match else "  FAIL")
            checks.append((
                f"{table} row count match", row_match,
                f"local={local_rows} snowflake={snowflake_rows}",
            ))

            pk = PRIMARY_KEYS[table]
            dupes = _duplicate_pk_count(cur, table, pk)
            nulls = _null_pk_count(cur, table, pk)
            checks.append((f"{table} no duplicate {pk}", dupes == 0, f"{dupes} duplicate keys"))
            checks.append((f"{table} no null {pk}", nulls == 0, f"{nulls} null keys"))
    finally:
        conn.close()

    print("\n" + "=" * 60)
    print("NEXORA SNOWFLAKE RAW LOAD VALIDATION")
    print("=" * 60)
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print("-" * 60)
    passed_count = sum(1 for _, p, _ in checks if p)
    failed_count = len(checks) - passed_count
    print(f"Tables checked: {len(RAW_TABLES)}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print("=" * 60)
    return failed_count == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
