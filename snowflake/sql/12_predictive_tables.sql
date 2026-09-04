-- NEXORA Phase 4: predictive analytics output tables.
--
-- These hold the RESULTS of the Python model pipelines in models/ -- no
-- computation happens here. Every pipeline does a full refresh (TRUNCATE +
-- bulk insert via models/common.py's write_table, reused unchanged from
-- mining/common.py), safe to rerun idempotently. CORE, RAW, STAGING, and
-- every existing ANALYTICS view/table are only ever read by Phase 4 code,
-- never written.
--
-- Run once, before the first pipeline run:
--
--     snowsql -f snowflake/sql/12_predictive_tables.sql

USE DATABASE NEXORA_DB;
USE SCHEMA ANALYTICS;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- ML_CUSTOMER_RISK -- grain: one row per current customer.
-- Source: models/customer_churn.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.ML_CUSTOMER_RISK (
    customer_id         VARCHAR       NOT NULL,
    risk_probability      NUMBER(8,6),
    predicted_class        NUMBER(1,0),   -- 1 = predicted churn/high-risk, 0 = not
    risk_level              VARCHAR,        -- Low / Medium / High, banded from risk_probability
    model_version            VARCHAR       NOT NULL,
    generated_at              TIMESTAMP_NTZ NOT NULL,
    PRIMARY KEY (customer_id)
);

-- ============================================================
-- ML_PROJECT_RISK -- grain: one row per project.
-- Source: models/project_risk.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.ML_PROJECT_RISK (
    project_id            VARCHAR       NOT NULL,
    risk_probability        NUMBER(8,6),
    predicted_risk_class     NUMBER(1,0),   -- 1 = predicted delayed, 0 = predicted on-time
    risk_level                VARCHAR,
    model_version               VARCHAR       NOT NULL,
    generated_at                 TIMESTAMP_NTZ NOT NULL,
    PRIMARY KEY (project_id)
);

-- ============================================================
-- ML_PAYMENT_DELAY -- grain: one row per invoice with a resolvable
-- customer payment-history feature set (see docs/predictive_analytics.md).
-- Source: models/payment_delay.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.ML_PAYMENT_DELAY (
    invoice_id            VARCHAR       NOT NULL,
    customer_id             VARCHAR       NOT NULL,
    delay_probability         NUMBER(8,6),
    predicted_delay             NUMBER(1,0),   -- 1 = predicted late payment, 0 = predicted on-time
    risk_level                    VARCHAR,
    model_version                   VARCHAR       NOT NULL,
    generated_at                     TIMESTAMP_NTZ NOT NULL,
    PRIMARY KEY (invoice_id)
);

-- ============================================================
-- ML_REVENUE_FORECAST -- grain: one row per forecasted future month.
-- Source: models/revenue_forecast.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.ML_REVENUE_FORECAST (
    forecast_date          DATE          NOT NULL,
    predicted_revenue        NUMBER(18,2),
    lower_bound                NUMBER(18,2),
    upper_bound                NUMBER(18,2),
    model_version                VARCHAR       NOT NULL,
    generated_at                  TIMESTAMP_NTZ NOT NULL,
    PRIMARY KEY (forecast_date)
);
