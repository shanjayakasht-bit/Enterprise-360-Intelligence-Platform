-- NEXORA Phase 2A: database, warehouse, and schema setup.
-- Run once with a role that can create databases/warehouses (e.g. SYSADMIN).
--
--     snowsql -f snowflake/sql/01_database_setup.sql
--
-- Idempotent: safe to re-run.

CREATE DATABASE IF NOT EXISTS NEXORA_DB
    COMMENT = 'NEXORA Enterprise Decision Intelligence Platform';

CREATE WAREHOUSE IF NOT EXISTS NEXORA_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'NEXORA ETL and analytics warehouse';

USE DATABASE NEXORA_DB;

-- Phase 2A uses RAW only. STAGING / CORE / ANALYTICS are created now so the
-- full architecture exists, but nothing is loaded into them yet.
CREATE SCHEMA IF NOT EXISTS RAW
    COMMENT = 'Phase 2A (active): raw ingested data, 1:1 with source CSVs, no business transformations';

CREATE SCHEMA IF NOT EXISTS STAGING
    COMMENT = 'Phase 2B (not yet in use): cleaned/typed staging layer';

CREATE SCHEMA IF NOT EXISTS CORE
    COMMENT = 'Phase 2C (not yet in use): dimensional model';

CREATE SCHEMA IF NOT EXISTS ANALYTICS
    COMMENT = 'Phase 2D (not yet in use): analytics-ready marts';

USE WAREHOUSE NEXORA_WH;
USE SCHEMA NEXORA_DB.RAW;
