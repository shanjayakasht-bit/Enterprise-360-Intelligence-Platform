"""Runs the Phase 2C STAGING -> CORE load. Run as:

    python -m etl.load_core

Executes, in order: snowflake/sql/06_core_dimensions.sql (dimension/sequence
setup), snowflake/sql/07_core_facts.sql (fact table setup), then
snowflake/sql/08_core_load.sql section-by-section (parsed via its
`-- @section: NAME` marker comments) -- those three files are the single
source of truth; this script only executes them and reports the result.
Only STAGING rows with _data_quality_status IN ('VALID','WARNING') are ever
read; RAW and STAGING are never written to. Stops at the first section that
fails rather than continuing with a partial CORE load.
"""

import logging
import re
import sys
from pathlib import Path

from etl.snowflake_connection import get_connection
from etl.transform_staging import _split_statements

ROOT_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT_DIR / "snowflake" / "sql"
DIMENSIONS_SQL = SQL_DIR / "06_core_dimensions.sql"
FACTS_SQL = SQL_DIR / "07_core_facts.sql"
LOAD_SQL = SQL_DIR / "08_core_load.sql"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexora.load_core")

# (section marker name, CORE table it loads, STAGING source table for the
# "eligible source rows" count -- None for reference dimensions that union
# several STAGING tables rather than reading one). Order matches
# 08_core_load.sql, which already respects FK dependencies (dimensions
# before facts; DIM_REGION/DIM_DEPARTMENT before DIM_EMPLOYEE before
# DIM_CUSTOMER).
SECTIONS = [
    ("DIM_DATE", "CORE.DIM_DATE", None),
    ("DIM_REGION", "CORE.DIM_REGION", None),
    ("DIM_DEPARTMENT", "CORE.DIM_DEPARTMENT", None),
    ("DIM_SERVICE", "CORE.DIM_SERVICE", None),
    ("DIM_EMPLOYEE", "CORE.DIM_EMPLOYEE", "STAGING.STG_EMPLOYEES"),
    ("DIM_CUSTOMER", "CORE.DIM_CUSTOMER", "STAGING.STG_CUSTOMERS"),
    ("FACT_LEADS", "CORE.FACT_LEADS", "STAGING.STG_LEADS"),
    ("FACT_DEALS", "CORE.FACT_DEALS", "STAGING.STG_DEALS"),
    ("FACT_SUBSCRIPTIONS", "CORE.FACT_SUBSCRIPTIONS", "STAGING.STG_SUBSCRIPTIONS"),
    ("FACT_PROJECTS", "CORE.FACT_PROJECTS", "STAGING.STG_PROJECTS"),
    ("FACT_INVOICES", "CORE.FACT_INVOICES", "STAGING.STG_INVOICES"),
    ("FACT_PAYMENTS", "CORE.FACT_PAYMENTS", "STAGING.STG_PAYMENTS"),
    ("FACT_SUPPORT", "CORE.FACT_SUPPORT", "STAGING.STG_SUPPORT_TICKETS"),
    ("FACT_CUSTOMER_ACTIVITY", "CORE.FACT_CUSTOMER_ACTIVITY", "STAGING.STG_CUSTOMER_ACTIVITY"),
]

_SECTION_MARKER = re.compile(r"^--\s*@section:\s*(\S+)\s*$")


def _parse_sections(sql_text):
    """Splits 08_core_load.sql on its '-- @section: NAME' marker comments
    into {name: [statement, ...]}, using the same quote-aware statement
    splitter as etl/transform_staging.py."""
    sections_raw = {}
    current, buf = None, []
    for line in sql_text.splitlines():
        m = _SECTION_MARKER.match(line.strip())
        if m:
            if current is not None:
                sections_raw[current] = "\n".join(buf)
            current, buf = m.group(1), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections_raw[current] = "\n".join(buf)
    return {name: _split_statements(text) for name, text in sections_raw.items()}


def run_setup(cur):
    for label, path in [("dimension", DIMENSIONS_SQL), ("fact", FACTS_SQL)]:
        logger.info("Creating CORE %s tables from %s", label, path.relative_to(ROOT_DIR))
        statements = _split_statements(path.read_text(encoding="utf-8"))
        for stmt in statements:
            cur.execute(stmt)
        logger.info("%d %s-table statements executed", len(statements), label)


def load_all():
    conn = get_connection()
    results = []
    try:
        cur = conn.cursor()
        run_setup(cur)

        sections = _parse_sections(LOAD_SQL.read_text(encoding="utf-8"))
        logger.info("Loaded %d sections from %s", len(sections), LOAD_SQL.relative_to(ROOT_DIR))

        for name, core_table, source_table in SECTIONS:
            statements = sections.get(name)
            if not statements:
                logger.error("[%s] no statements found in %s", name, LOAD_SQL.name)
                results.append({"section": name, "status": "FAILED", "error": "no statements found for section"})
                break

            try:
                source_rows = None
                if source_table:
                    cur.execute(f"SELECT COUNT(*) FROM {source_table} WHERE _data_quality_status IN ('VALID','WARNING')")
                    source_rows = cur.fetchone()[0]
                    logger.info("[%s] loading from %s (eligible source rows=%d)", name, source_table, source_rows)
                else:
                    logger.info("[%s] loading (reference dimension, unioned across multiple STAGING tables)", name)

                for stmt in statements:
                    cur.execute(stmt)

                cur.execute(f"SELECT COUNT(*) FROM {core_table}")
                loaded_rows = cur.fetchone()[0]

                logger.info(
                    "[%s] OK loaded_rows=%d%s", name, loaded_rows,
                    f" source_rows={source_rows}" if source_rows is not None else "",
                )
                results.append({
                    "section": name, "core_table": core_table, "source_table": source_table,
                    "source_rows": source_rows, "loaded_rows": loaded_rows, "status": "OK",
                })
            except Exception as exc:
                logger.error("[%s] load FAILED: %s", name, exc)
                results.append({"section": name, "status": "FAILED", "error": str(exc)})
                break
    finally:
        conn.close()

    logger.info("CORE load summary:")
    for r in results:
        if r["status"] == "OK":
            src = f"source_rows={r['source_rows']}" if r["source_rows"] is not None else "source_rows=n/a"
            logger.info("  %-24s %-28s %-22s loaded_rows=%-8d status=OK", r["section"], r["core_table"], src, r["loaded_rows"])
        else:
            logger.info("  %-24s status=FAILED error=%s", r["section"], r["error"])

    all_ok = len(results) == len(SECTIONS) and all(r["status"] == "OK" for r in results)
    return results, all_ok


if __name__ == "__main__":
    _, ok = load_all()
    sys.exit(0 if ok else 1)
