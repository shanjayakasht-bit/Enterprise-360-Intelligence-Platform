"""Snowflake connection helper shared by the NEXORA ETL scripts.

Credentials are loaded ONLY from environment variables (via a local .env,
never committed -- see .env.example). Nothing is hardcoded here. Run
standalone to test connectivity:

    python -m etl.snowflake_connection
"""

import os

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV_VARS = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_ROLE",
]

DATABASE = os.getenv("SNOWFLAKE_DATABASE", "NEXORA_DB")
RAW_SCHEMA = "RAW"
STAGING_SCHEMA = "STAGING"
STAGE_NAME = "NEXORA_RAW_STAGE"
FILE_FORMAT_NAME = "NEXORA_CSV_FORMAT"

# RAW table name -> source CSV filename in data/raw/, in FK-safe dependency order.
RAW_TABLES = [
    ("CUSTOMERS", "customers.csv"),
    ("EMPLOYEES", "employees.csv"),
    ("LEADS", "leads.csv"),
    ("DEALS", "deals.csv"),
    ("SUBSCRIPTIONS", "subscriptions.csv"),
    ("PROJECTS", "projects.csv"),
    ("INVOICES", "invoices.csv"),
    ("PAYMENTS", "payments.csv"),
    ("SUPPORT_TICKETS", "support_tickets.csv"),
    ("CUSTOMER_ACTIVITY", "customer_activity.csv"),
]

# STAGING table name -> source RAW table name, same FK-safe dependency order.
STAGING_TABLES = [
    ("STG_CUSTOMERS", "CUSTOMERS"),
    ("STG_EMPLOYEES", "EMPLOYEES"),
    ("STG_LEADS", "LEADS"),
    ("STG_DEALS", "DEALS"),
    ("STG_SUBSCRIPTIONS", "SUBSCRIPTIONS"),
    ("STG_PROJECTS", "PROJECTS"),
    ("STG_INVOICES", "INVOICES"),
    ("STG_PAYMENTS", "PAYMENTS"),
    ("STG_SUPPORT_TICKETS", "SUPPORT_TICKETS"),
    ("STG_CUSTOMER_ACTIVITY", "CUSTOMER_ACTIVITY"),
]


def _missing_env_vars():
    return [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]


def get_connection():
    """Opens a new Snowflake connection using only environment variables.

    Raises a clear RuntimeError (rather than a raw connector traceback) if
    any required variable is missing, so a bad .env fails fast.
    """
    missing = _missing_env_vars()
    if missing:
        raise RuntimeError(
            "Missing required Snowflake environment variables: "
            f"{', '.join(missing)}. Copy .env.example to .env and fill in real values."
        )
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ["SNOWFLAKE_ROLE"],
        schema=RAW_SCHEMA,
    )


if __name__ == "__main__":
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT CURRENT_VERSION(), CURRENT_ACCOUNT(), CURRENT_WAREHOUSE(), "
            "CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_ROLE()"
        )
        version, account, warehouse, database, schema, role = cur.fetchone()
        print("Connected to Snowflake successfully.")
        print(f"  Snowflake version : {version}")
        print(f"  Account           : {account}")
        print(f"  Warehouse         : {warehouse}")
        print(f"  Database          : {database}")
        print(f"  Schema            : {schema}")
        print(f"  Role              : {role}")
    finally:
        conn.close()
