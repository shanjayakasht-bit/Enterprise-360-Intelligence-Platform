"""Shared Snowflake I/O helpers for the Phase 3 data mining pipelines.

Every mining script reads from NEXORA_DB.ANALYTICS/CORE (never RAW/STAGING,
never writing back to either) and writes its results into one of the four
ANALYTICS.DM_* tables created by snowflake/sql/11_data_mining_tables.sql,
using a full-refresh TRUNCATE + bulk-insert -- acceptable for this phase per
the brief, and safe to rerun any number of times without duplicating rows.
"""

import logging
from datetime import datetime, timezone

import pandas as pd
from snowflake.connector.pandas_tools import write_pandas

from etl.snowflake_connection import DATABASE, get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MINING_SCHEMA = "ANALYTICS"


def get_logger(name):
    return logging.getLogger(f"nexora.mining.{name}")


def run_timestamp():
    """One shared UTC timestamp per pipeline run, used for every row's
    generated_at column so a single run is trivially identifiable."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fetch_dataframe(sql):
    """Runs a read-only SELECT and returns the result as a pandas DataFrame
    with upper-cased column names (matching Snowflake's default identifier
    casing)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df.columns = [c.upper() for c in df.columns]
    return df


def write_table(df, table_name, schema=MINING_SCHEMA):
    """Full-refresh write: TRUNCATE the target DM_* table, then bulk-load
    the dataframe via write_pandas. Table must already exist (created by
    snowflake/sql/11_data_mining_tables.sql) -- this never issues DDL, and
    never touches anything outside ANALYTICS.<table_name>.

    Returns the number of rows written.
    """
    logger = get_logger("common")
    if df.empty:
        logger.warning("[%s] dataframe is empty, nothing to write", table_name)

    df = df.copy()
    if "GENERATED_AT" in df.columns:
        # write_pandas' Arrow/Parquet path silently corrupts a datetime64
        # column here (observed: writes a garbage far-future date, e.g.
        # year 56678841, apparently an epoch-unit scaling bug somewhere in
        # the pandas-Timestamp -> Arrow -> Snowflake TIMESTAMP_NTZ path
        # with this connector/pyarrow combination) -- confirmed by writing
        # a minimal repro table and reading the raw stored value back with
        # TO_VARCHAR. Writing it as a plain formatted string instead and
        # letting the TIMESTAMP_NTZ column's implicit cast parse it on
        # INSERT sidesteps that path entirely and was verified correct.
        df["GENERATED_AT"] = pd.to_datetime(df["GENERATED_AT"]).dt.strftime("%Y-%m-%d %H:%M:%S.%f")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"TRUNCATE TABLE {DATABASE}.{schema}.{table_name}")
        # quote_identifiers defaults to True, which quote-matches write_pandas'
        # generated INSERT column list against the target table's actual
        # (uppercase-folded) column names -- our dataframes use upper-cased
        # column names throughout, so this lines up correctly.
        success, n_chunks, n_rows, _ = write_pandas(
            conn, df, table_name=table_name, database=DATABASE, schema=schema,
        )
        if not success:
            raise RuntimeError(f"write_pandas reported failure writing {table_name}")
        logger.info("[%s] wrote %d rows (%d chunks)", table_name, n_rows, n_chunks)
        return n_rows
    finally:
        conn.close()
