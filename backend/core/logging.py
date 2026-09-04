"""Structured logging setup for the API. Every request gets one summary log
line (route, status, duration, and -- where applicable -- which Snowflake
query operation served it), via the middleware registered in
backend/main.py. Never logs the password, connection string, or full row
payloads -- see backend/db/snowflake.py for the query-level logging that
feeds this.
"""

import logging
import sys

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(level=logging.INFO):
    root = logging.getLogger("nexora.api")
    if root.handlers:
        return root  # idempotent -- safe to call from multiple import sites
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    root.propagate = False
    return root


def get_logger(name):
    return logging.getLogger(f"nexora.api.{name}")
