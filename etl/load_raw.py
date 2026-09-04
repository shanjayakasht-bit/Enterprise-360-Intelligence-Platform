"""Loads staged CSV files from @NEXORA_DB.RAW.NEXORA_RAW_STAGE into the
matching RAW tables via COPY INTO. Run as:

    python -m etl.load_raw                  append mode (default): safe, incremental.
                                              Snowflake's load history skips a staged
                                              file already loaded into a table, so
                                              re-running never silently duplicates rows.
    python -m etl.load_raw --mode reload     full reload: TRUNCATEs each RAW table
                                              first, then force-loads every staged file.
                                              Only runs when explicitly requested.
"""

import argparse
import csv
import logging
import sys
from pathlib import Path

from etl.snowflake_connection import DATABASE, FILE_FORMAT_NAME, RAW_SCHEMA, RAW_TABLES, STAGE_NAME, get_connection

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data" / "raw"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexora.load_raw")


def _read_csv_header(path):
    """Reads the actual local CSV header so COPY INTO's column list always
    matches the source file, independent of RAW table column order/extras
    (e.g. the ingestion-only _loaded_at column)."""
    with open(path, newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def load_table(cur, table, filename, mode):
    qualified_table = f"{DATABASE}.{RAW_SCHEMA}.{table}"
    stage_file = f"@{DATABASE}.{RAW_SCHEMA}.{STAGE_NAME}/{filename}"
    columns = ", ".join(_read_csv_header(DATA_DIR / filename))

    if mode == "reload":
        logger.info("[%s] reload mode: truncating table before load", table)
        cur.execute(f"TRUNCATE TABLE {qualified_table}")

    copy_sql = (
        f"COPY INTO {qualified_table} ({columns}) "
        f"FROM {stage_file} "
        f"FILE_FORMAT = (FORMAT_NAME = {DATABASE}.{RAW_SCHEMA}.{FILE_FORMAT_NAME}) "
        f"ON_ERROR = 'ABORT_STATEMENT'"
        + (" FORCE = TRUE" if mode == "reload" else "")
    )
    logger.info("[%s] loading from %s (mode=%s)", table, stage_file, mode)
    cur.execute(copy_sql)
    rows = cur.fetchall()
    result_columns = [c[0].lower() for c in cur.description]

    rows_loaded = 0
    errors_seen = 0
    status = "ALREADY_LOADED" if not rows else "LOADED"
    for r in rows:
        record = dict(zip(result_columns, r))
        rows_loaded += record.get("rows_loaded") or 0
        errors_seen += record.get("errors_seen") or 0
        status = record.get("status", status)

    logger.info(
        "[%s] source=%s rows_loaded=%d errors=%d status=%s",
        table, filename, rows_loaded, errors_seen, status,
    )
    return {
        "table": table,
        "file": filename,
        "rows_loaded": rows_loaded,
        "errors": errors_seen,
        "status": status,
    }


def load_all(mode="append"):
    assert mode in ("append", "reload"), f"unknown mode: {mode}"
    conn = get_connection()
    summary = []
    try:
        cur = conn.cursor()
        for table, filename in RAW_TABLES:
            local_path = DATA_DIR / filename
            if not local_path.exists():
                logger.error("[%s] MISSING local file, skipping: %s", table, local_path)
                summary.append({"table": table, "file": filename, "rows_loaded": 0, "errors": 1, "status": "MISSING_FILE"})
                continue
            summary.append(load_table(cur, table, filename, mode))
    finally:
        conn.close()

    logger.info("Load complete (mode=%s):", mode)
    total_rows, total_errors = 0, 0
    for r in summary:
        logger.info(
            "  %-20s file=%-24s rows_loaded=%-8d errors=%-4d status=%s",
            r["table"], r["file"], r["rows_loaded"], r["errors"], r["status"],
        )
        total_rows += r["rows_loaded"]
        total_errors += r["errors"]
    logger.info("Total rows loaded: %d, total errors: %d", total_rows, total_errors)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load staged NEXORA CSVs into RAW tables.")
    parser.add_argument(
        "--mode", choices=["append", "reload"], default="append",
        help="append (default): safe incremental load. reload: TRUNCATEs each RAW table first.",
    )
    args = parser.parse_args()

    results = load_all(args.mode)
    any_errors = any(r["errors"] for r in results)
    sys.exit(1 if any_errors else 0)
