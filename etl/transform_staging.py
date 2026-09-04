"""Runs the Phase 2B RAW -> STAGING pipeline. Run as:

    python -m etl.transform_staging

Reads its SQL from snowflake/sql/04_staging_tables.sql (setup, idempotent)
and snowflake/sql/05_staging_transformations.sql (full-refresh transform,
one TRUNCATE + INSERT block per table) -- those files are the single source
of truth; this script only executes them table-by-table and reports the
result. RAW is only ever read here (SELECT COUNT / SELECT ... FROM RAW.*),
never written. Stops at the first table whose transformation fails rather
than continuing with a partial STAGING refresh.
"""

import logging
import re
import sys
from pathlib import Path

from etl.snowflake_connection import STAGING_TABLES, get_connection

ROOT_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT_DIR / "snowflake" / "sql"
STAGING_SETUP_SQL = SQL_DIR / "04_staging_tables.sql"
STAGING_TRANSFORM_SQL = SQL_DIR / "05_staging_transformations.sql"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexora.transform_staging")


def _split_statements(sql_text):
    """Strips '--' line comments, then splits the file into individual
    statements on top-level ';' characters. A semicolon inside a quoted
    string literal -- e.g. the '; ' separator used to join data-quality
    issue text -- must NOT be treated as a statement boundary, so this
    tracks single-quote string state (handling '' as an escaped quote)
    rather than doing a plain str.split(';')."""
    kept_lines = [line for line in sql_text.splitlines() if not line.strip().startswith("--")]
    cleaned = "\n".join(kept_lines)

    statements = []
    buf = []
    in_string = False
    i, n = 0, len(cleaned)
    while i < n:
        ch = cleaned[i]
        if ch == "'":
            if in_string and i + 1 < n and cleaned[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_string = not in_string
            buf.append(ch)
        elif ch == ";" and not in_string:
            statements.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return [s.strip() for s in statements if s.strip()]


def _statements_for_table(statements, table_name):
    pattern = re.compile(rf"STAGING\.{re.escape(table_name)}\b", re.IGNORECASE)
    return [s for s in statements if pattern.search(s)]


def run_table_setup(cur):
    logger.info("Creating STAGING tables from %s", STAGING_SETUP_SQL.relative_to(ROOT_DIR))
    statements = _split_statements(STAGING_SETUP_SQL.read_text(encoding="utf-8"))
    for stmt in statements:
        cur.execute(stmt)
    logger.info("STAGING table setup complete (%d statements executed)", len(statements))


def transform_all():
    conn = get_connection()
    results = []
    try:
        cur = conn.cursor()
        run_table_setup(cur)

        all_statements = _split_statements(STAGING_TRANSFORM_SQL.read_text(encoding="utf-8"))
        logger.info("Loaded %d statements from %s", len(all_statements), STAGING_TRANSFORM_SQL.relative_to(ROOT_DIR))

        for stg_table, raw_table in STAGING_TABLES:
            table_statements = _statements_for_table(all_statements, stg_table)
            if not table_statements:
                logger.error("[%s] no TRUNCATE/INSERT statements found in %s", stg_table, STAGING_TRANSFORM_SQL.name)
                results.append({"table": stg_table, "status": "FAILED", "error": "no statements found for table"})
                break

            try:
                cur.execute(f"SELECT COUNT(*) FROM RAW.{raw_table}")
                source_rows = cur.fetchone()[0]
                logger.info("[%s] transforming from RAW.%s (source rows=%d)", stg_table, raw_table, source_rows)

                for stmt in table_statements:
                    cur.execute(stmt)

                cur.execute(f"SELECT COUNT(*) FROM STAGING.{stg_table}")
                staged_rows = cur.fetchone()[0]

                logger.info("[%s] OK source_rows=%d staged_rows=%d", stg_table, source_rows, staged_rows)
                results.append({
                    "table": stg_table, "source_table": raw_table,
                    "source_rows": source_rows, "staged_rows": staged_rows, "status": "OK",
                })
            except Exception as exc:
                logger.error("[%s] transformation FAILED: %s", stg_table, exc)
                results.append({"table": stg_table, "status": "FAILED", "error": str(exc)})
                break
    finally:
        conn.close()

    logger.info("Transform summary:")
    for r in results:
        if r["status"] == "OK":
            logger.info(
                "  %-24s source=RAW.%-20s source_rows=%-8d staged_rows=%-8d status=OK",
                r["table"], r["source_table"], r["source_rows"], r["staged_rows"],
            )
        else:
            logger.info("  %-24s status=FAILED error=%s", r["table"], r["error"])

    all_ok = len(results) == len(STAGING_TABLES) and all(r["status"] == "OK" for r in results)
    return results, all_ok


if __name__ == "__main__":
    _, ok = transform_all()
    sys.exit(0 if ok else 1)
