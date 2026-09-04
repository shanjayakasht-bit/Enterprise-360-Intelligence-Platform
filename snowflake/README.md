# NEXORA Snowflake — Phase 2A: RAW Data Ingestion

Loads the validated full CSV datasets from `data/raw/` into Snowflake's `RAW`
schema. No transformations, no STAGING/CORE/ANALYTICS modeling yet — those
schemas are created for the target architecture but stay empty in this phase.

## Architecture

- **Database**: `NEXORA_DB`
- **Warehouse**: `NEXORA_WH` (XSMALL, `AUTO_SUSPEND=60`, `AUTO_RESUME=TRUE`)
- **Schemas**: `RAW` (active this phase), `STAGING`, `CORE`, `ANALYTICS` (created, unused)
- **File format**: `NEXORA_DB.RAW.NEXORA_CSV_FORMAT`
- **Stage**: `NEXORA_DB.RAW.NEXORA_RAW_STAGE`
- **Tables**: `RAW.CUSTOMERS`, `RAW.EMPLOYEES`, `RAW.LEADS`, `RAW.DEALS`,
  `RAW.SUBSCRIPTIONS`, `RAW.PROJECTS`, `RAW.INVOICES`, `RAW.PAYMENTS`,
  `RAW.SUPPORT_TICKETS`, `RAW.CUSTOMER_ACTIVITY` — column names/order match
  the actual `data/raw/*.csv` headers, plus one ingestion-only `_loaded_at`
  timestamp column per table.

## Setup order

Run the SQL once, with a role that can create databases/warehouses:

```
snowsql -f snowflake/sql/01_database_setup.sql
snowsql -f snowflake/sql/02_file_format_stage.sql
snowsql -f snowflake/sql/03_raw_tables.sql
```

All three scripts are idempotent (`CREATE ... IF NOT EXISTS`) and safe to re-run.

## Python pipeline

1. `python -m etl.snowflake_connection` — test connectivity
2. `python -m etl.upload_to_stage` — PUT `data/raw/*.csv` to `@NEXORA_DB.RAW.NEXORA_RAW_STAGE`
3. `python -m etl.load_raw` — `COPY INTO` each RAW table (append mode by default; `--mode reload` truncates first)
4. `python -m etl.validate_load` — compares local vs. Snowflake row counts, checks primary keys, table existence, and stage contents

See the repo root `.env.example` for the required environment variables — copy it to `.env` (git-ignored) and fill in real credentials. Never commit `.env`.

## Out of scope for Phase 2A

STAGING transformations, CORE dimensional modeling, ANALYTICS marts, ML, and any frontend/backend work start in later phases.
