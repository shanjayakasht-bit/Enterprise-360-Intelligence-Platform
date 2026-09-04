"""JSON-safe conversion for values coming back from the Snowflake
connector: Decimal, date, datetime, and (defensively) any numpy scalar
type, none of which are natively JSON-serializable. Applied once, in
backend/db/snowflake.py's row-to-dict conversion, so every layer above it
(services, routers, Pydantic models) only ever sees plain Python
int/float/str/bool/None/date/datetime.
"""

import datetime
from decimal import Decimal


def sanitize_value(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        # Whole-valued Decimals (counts, IDs stored as NUMBER) become int;
        # anything with a fractional part becomes float.
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value  # FastAPI/Pydantic serialize these natively -- kept as-is
    # numpy scalars (e.g. if a value ever passes through pandas upstream)
    # expose .item() to convert to the equivalent native Python type.
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return value
    return value


def sanitize_row(row, columns):
    return {col.lower(): sanitize_value(val) for col, val in zip(columns, row)}


def sanitize_rows(rows, columns):
    return [sanitize_row(row, columns) for row in rows]
