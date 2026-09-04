-- NEXORA Phase 2C: CORE dimension schemas.
--
-- Source: NEXORA_DB.STAGING (VALID/WARNING rows only -- enforced in
-- 08_core_load.sql, not here). RAW and STAGING are never written to by
-- anything in Phase 2C.
--
-- Surrogate keys are warehouse-generated integers (via the SEQUENCE objects
-- below); original business/natural keys (customer_id, employee_id, ...)
-- are always kept alongside them. Every dimension reserves surrogate key
-- -1 for an "Unknown member" row, used when a fact can't resolve a real
-- dimension lookup (see docs/dimensional_model.md) -- never NULL, never a
-- dropped fact row.
--
-- DIM_CUSTOMER and DIM_EMPLOYEE implement SCD Type 2 (effective_from /
-- effective_to / is_current). DIM_SERVICE, DIM_REGION and DIM_DEPARTMENT
-- are simple Type 1 reference dimensions -- current value only, no history.
--
-- Run after snowflake/sql/05_staging_transformations.sql (Phase 2B) and
-- once against the RAW/STAGING/CORE schemas already created in
-- 01_database_setup.sql:
--
--     snowsql -f snowflake/sql/06_core_dimensions.sql

USE DATABASE NEXORA_DB;
USE SCHEMA CORE;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- Surrogate key sequences (DIM_DATE uses a deterministic YYYYMMDD key
-- instead, so it needs no sequence).
-- ============================================================
CREATE SEQUENCE IF NOT EXISTS CORE.SEQ_CUSTOMER_KEY START = 1 INCREMENT = 1;
CREATE SEQUENCE IF NOT EXISTS CORE.SEQ_EMPLOYEE_KEY START = 1 INCREMENT = 1;
CREATE SEQUENCE IF NOT EXISTS CORE.SEQ_SERVICE_KEY START = 1 INCREMENT = 1;
CREATE SEQUENCE IF NOT EXISTS CORE.SEQ_REGION_KEY START = 1 INCREMENT = 1;
CREATE SEQUENCE IF NOT EXISTS CORE.SEQ_DEPARTMENT_KEY START = 1 INCREMENT = 1;

-- ============================================================
-- DIM_DATE -- one row per calendar day, 2018-01-01 .. 2029-12-31.
-- Covers the full observed range of every date column across all ten
-- STAGING tables (actual min/max checked live: 2018-09-05 .. 2028-09-04),
-- with a safety margin on both ends. date_key is an integer YYYYMMDD, e.g.
-- 2026-09-04 -> 20260904. One extra row, date_key = -1, is the Unknown
-- member for facts whose source date is NULL (e.g. an unresolved ticket's
-- resolution_date).
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.DIM_DATE (
    date_key        NUMBER(9,0)  NOT NULL,
    full_date       DATE,
    day_of_month    NUMBER(2,0),
    day_name        VARCHAR(10),
    day_of_week     NUMBER(1,0),
    week_of_year    NUMBER(2,0),
    month_number    NUMBER(2,0),
    month_name      VARCHAR(10),
    quarter         NUMBER(1,0),
    year            NUMBER(4,0),
    is_weekend      BOOLEAN,
    PRIMARY KEY (date_key)
);

-- ============================================================
-- DIM_REGION -- Type 1. Grain: one row per distinct region name, as it
-- appears across STG_CUSTOMERS.region / STG_EMPLOYEES.region / STG_DEALS.region.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.DIM_REGION (
    region_key      NUMBER(10,0) NOT NULL,
    region_name     VARCHAR      NOT NULL,
    _core_loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (region_key)
);

-- ============================================================
-- DIM_DEPARTMENT -- Type 1. Grain: one row per distinct STG_EMPLOYEES.department.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.DIM_DEPARTMENT (
    department_key   NUMBER(10,0) NOT NULL,
    department_name  VARCHAR      NOT NULL,
    _core_loaded_at  TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (department_key)
);

-- ============================================================
-- DIM_SERVICE -- Type 1. A conformed "what NEXORA offering is this row
-- about" dimension, built from the three distinct STAGING columns that
-- each describe an offering at a different grain: the product sold on a
-- deal, the plan tier of a subscription, and the engagement type of a
-- project. service_category tells them apart; service_name is the actual
-- STAGING value, unmodified. See docs/dimensional_model.md for why these
-- three were conformed into one dimension instead of three.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.DIM_SERVICE (
    service_key       NUMBER(10,0) NOT NULL,
    service_name      VARCHAR      NOT NULL,
    service_category  VARCHAR      NOT NULL, -- 'Product' | 'Subscription Plan' | 'Project Type'
    _core_loaded_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (service_key)
);

-- ============================================================
-- DIM_CUSTOMER -- SCD Type 2. Grain: one row per customer PER VERSION.
-- customer_id is the stable business key; customer_key is the surrogate
-- key facts reference, unique per version. Exactly one row per customer_id
-- has is_current = TRUE at any time (enforced by the load logic in
-- 08_core_load.sql, checked by etl/validate_core.py). _row_hash fingerprints
-- every tracked attribute so a reload can detect "nothing changed" and add
-- no new version -- see docs/dimensional_model.md for the exact algorithm.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.DIM_CUSTOMER (
    customer_key                  NUMBER(10,0) NOT NULL,
    customer_id                   VARCHAR      NOT NULL,
    company_name                  VARCHAR,
    industry                      VARCHAR,
    segment                       VARCHAR,
    region_key                    NUMBER(10,0),
    country                       VARCHAR,
    account_manager_key           NUMBER(10,0),
    subscription_plan             VARCHAR,
    signup_date                   DATE,
    contract_start_date           DATE,
    renewal_date                  DATE,
    annual_contract_value         NUMBER(15,2),
    product_usage_score           NUMBER(6,2),
    engagement_score              NUMBER(6,2),
    satisfaction_score            NUMBER(6,2),
    support_ticket_count_recent   NUMBER(10,0),
    avg_payment_delay_days        NUMBER(8,2),
    days_to_renewal               NUMBER(10,0),
    churn_risk_score               NUMBER(6,2),
    churn_risk_category           VARCHAR,
    effective_from                DATE         NOT NULL,
    effective_to                  DATE,
    is_current                    BOOLEAN      NOT NULL,
    _row_hash                     NUMBER(38,0),
    _source_loaded_at             TIMESTAMP_NTZ,
    _core_loaded_at               TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (customer_key)
);

-- ============================================================
-- DIM_EMPLOYEE -- SCD Type 2. Grain: one row per employee PER VERSION.
-- manager_id is kept as the plain business-key (not resolved to a
-- self-referencing surrogate key) -- see docs/dimensional_model.md for why.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.DIM_EMPLOYEE (
    employee_key      NUMBER(10,0) NOT NULL,
    employee_id       VARCHAR      NOT NULL,
    first_name        VARCHAR,
    last_name         VARCHAR,
    full_name         VARCHAR,
    email             VARCHAR,
    department_key    NUMBER(10,0),
    job_title         VARCHAR,
    region_key        NUMBER(10,0),
    hire_date         DATE,
    manager_id        VARCHAR,
    performance_score NUMBER(6,2),
    is_active         BOOLEAN,
    effective_from    DATE         NOT NULL,
    effective_to      DATE,
    is_current        BOOLEAN      NOT NULL,
    _row_hash         NUMBER(38,0),
    _source_loaded_at TIMESTAMP_NTZ,
    _core_loaded_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (employee_key)
);
