-- NEXORA Phase 2A: CSV file format and internal stage for RAW ingestion.
-- Run after 01_database_setup.sql:
--
--     snowsql -f snowflake/sql/02_file_format_stage.sql
--
-- Idempotent: safe to re-run.

USE DATABASE NEXORA_DB;
USE SCHEMA RAW;
USE WAREHOUSE NEXORA_WH;

CREATE OR REPLACE FILE FORMAT NEXORA_DB.RAW.NEXORA_CSV_FORMAT
    TYPE = 'CSV'
    SKIP_HEADER = 1
    FIELD_DELIMITER = ','
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF = ('', 'NULL', 'null')
    EMPTY_FIELD_AS_NULL = TRUE
    TRIM_SPACE = TRUE
    ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE
    COMMENT = 'Standard CSV format for NEXORA RAW ingestion from data/raw/';

CREATE STAGE IF NOT EXISTS NEXORA_DB.RAW.NEXORA_RAW_STAGE
    FILE_FORMAT = NEXORA_DB.RAW.NEXORA_CSV_FORMAT
    COMMENT = 'Internal stage for NEXORA data/raw/ CSVs, uploaded via etl/upload_to_stage.py before COPY INTO';
