"""Snowflake connection and query execution for the API.

This WRAPS the same connection logic already established in
etl/snowflake_connection.py (env-var-only credentials, one connection per
operation, explicit close) rather than importing that module directly: the
API is a long-running server reading typed settings from
backend.core.config.settings (pydantic-validated, loaded once at startup),
while etl.snowflake_connection is written for one-shot scripts that read
os.environ directly and call load_dotenv() at import time. Reusing that
module here would silently wire up a second, parallel config-loading path
inside a persistent server process. Both read the same single .env file
and the same six credential values -- nothing is duplicated or redefined,
only the loading mechanism differs, deliberately.

No connection pooling: every call opens a fresh connection and closes it in
a `finally` block, matching the pattern already used throughout this
project's etl/mining/models/decision_engine scripts. This is a known,
documented scalability limitation for Phase 6 (see docs/api_reference.md)
-- acceptable for a read-only, low-concurrency Phase 6 API, not something a
production deployment should keep as-is.
"""

import time
from contextlib import contextmanager

import snowflake.connector

from backend.core.config import settings
from backend.core.exceptions import DatabaseError
from backend.core.logging import get_logger
from backend.utils.serialization import sanitize_rows

logger = get_logger("db")


def get_connection():
    return snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        password=settings.snowflake_password.get_secret_value(),
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        role=settings.snowflake_role,
        schema="ANALYTICS",
    )


@contextmanager
def snowflake_cursor():
    conn = get_connection()
    try:
        yield conn.cursor()
    finally:
        conn.close()


def execute_query(sql, params=None, operation="query"):
    """Runs a SELECT and returns a list of lower-cased-key dicts with every
    value already JSON-safe (Decimal/date/datetime/numpy handled -- see
    backend/utils/serialization.py). Never interpolates params into the SQL
    string -- always passed through the connector's own parameter binding.
    """
    started = time.monotonic()
    try:
        with snowflake_cursor() as cur:
            cur.execute(sql, params) if params is not None else cur.execute(sql)
            columns = [c[0] for c in cur.description]
            rows = cur.fetchall()
    except snowflake.connector.errors.Error as exc:
        # Never forward the raw Snowflake error (may include SQL text or
        # connection detail) to the API layer / client -- log it here,
        # raise a generic DatabaseError the exception handler turns into a
        # safe 500.
        logger.error("[%s] Snowflake query failed after %.1fms: %s",
                     operation, (time.monotonic() - started) * 1000, exc)
        raise DatabaseError("A database error occurred while serving this request.") from exc

    duration_ms = (time.monotonic() - started) * 1000
    logger.info("[%s] %d rows in %.1fms", operation, len(rows), duration_ms)
    return sanitize_rows(rows, columns)


def execute_scalar(sql, params=None, operation="scalar"):
    rows = execute_query(sql, params=params, operation=operation)
    if not rows:
        return None
    return next(iter(rows[0].values()))


def health_check():
    """Lightweight connectivity probe for GET /api/v1/health -- a single
    cheap SELECT, not a real query against any ANALYTICS table."""
    try:
        with snowflake_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        logger.exception("Snowflake health check failed")
        return False
