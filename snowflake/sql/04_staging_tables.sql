-- NEXORA Phase 2B: STAGING table schemas.
--
-- One STG_* table per RAW table, same business columns (cleaned/typed) in
-- the same order as snowflake/sql/03_raw_tables.sql, plus four pipeline
-- metadata columns every staging table carries:
--
--   _source_loaded_at     TIMESTAMP_NTZ  -- copied from RAW._loaded_at (source ingestion time)
--   _staged_at            TIMESTAMP_NTZ  -- when this row was (re)staged
--   _data_quality_status  VARCHAR        -- VALID / WARNING / INVALID (see docs/staging_data_quality.md)
--   _data_quality_issue   VARCHAR        -- semicolon-separated list of triggered rules, NULL if none
--
-- Invalid rows are still loaded here, flagged rather than dropped -- see
-- docs/staging_data_quality.md for the full rule set. No business formulas
-- from Phase 1 are altered; this is cleaning/typing/flagging only.
--
-- Run after 03_raw_tables.sql:
--
--     snowsql -f snowflake/sql/04_staging_tables.sql

USE DATABASE NEXORA_DB;
USE SCHEMA STAGING;
USE WAREHOUSE NEXORA_WH;

CREATE TABLE IF NOT EXISTS STAGING.STG_CUSTOMERS (
    customer_id                    VARCHAR,
    company_name                   VARCHAR,
    industry                       VARCHAR,
    segment                        VARCHAR,
    region                         VARCHAR,
    country                        VARCHAR,
    account_manager_id             VARCHAR,
    subscription_plan              VARCHAR,
    signup_date                    DATE,
    contract_start_date            DATE,
    renewal_date                   DATE,
    annual_contract_value          NUMBER(15,2),
    product_usage_score            NUMBER(6,2),
    engagement_score                NUMBER(6,2),
    satisfaction_score             NUMBER(6,2),
    support_ticket_count_recent    NUMBER(10,0),
    avg_payment_delay_days         NUMBER(8,2),
    days_to_renewal                NUMBER(10,0),
    churn_risk_score                NUMBER(6,2),
    churn_risk_category            VARCHAR,
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_EMPLOYEES (
    employee_id                    VARCHAR,
    first_name                     VARCHAR,
    last_name                      VARCHAR,
    full_name                      VARCHAR,
    email                           VARCHAR,
    department                     VARCHAR,
    job_title                      VARCHAR,
    region                         VARCHAR,
    hire_date                      DATE,
    manager_id                     VARCHAR,
    performance_score              NUMBER(6,2),
    is_active                      BOOLEAN,
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_LEADS (
    lead_id                         VARCHAR,
    customer_id                    VARCHAR,
    lead_source                    VARCHAR,
    created_date                   DATE,
    assigned_salesperson_id        VARCHAR,
    status                          VARCHAR,
    lead_score                     NUMBER(6,2),
    converted_to_deal               BOOLEAN,
    converted_date                  DATE,
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_DEALS (
    deal_id                         VARCHAR,
    customer_id                    VARCHAR,
    lead_id                         VARCHAR,
    sales_rep_id                    VARCHAR,
    product                          VARCHAR,
    deal_stage                     VARCHAR,
    is_won                           BOOLEAN,
    deal_value                     NUMBER(15,2),
    discount_pct                    NUMBER(6,4),
    created_date                   DATE,
    close_date                     DATE,
    region                          VARCHAR,
    segment                         VARCHAR,
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_SUBSCRIPTIONS (
    subscription_id                 VARCHAR,
    customer_id                    VARCHAR,
    deal_id                         VARCHAR,
    plan                             VARCHAR,
    billing_cycle                   VARCHAR,
    start_date                     DATE,
    end_date                        DATE,
    mrr                              NUMBER(15,2),
    status                          VARCHAR,
    auto_renew                     BOOLEAN,
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_PROJECTS (
    project_id                      VARCHAR,
    customer_id                    VARCHAR,
    deal_id                         VARCHAR,
    project_manager_id              VARCHAR,
    project_type                    VARCHAR,
    start_date                     DATE,
    planned_end_date                DATE,
    actual_end_date                 DATE,
    status                          VARCHAR,
    completion_pct                  NUMBER(6,2),
    budget                          NUMBER(15,2),
    actual_cost                     NUMBER(15,2),
    budget_utilization_pct          NUMBER(8,2),
    cost_overrun_pct                NUMBER(8,2),
    project_risk_score              NUMBER(6,2),
    project_risk_category           VARCHAR,
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_INVOICES (
    invoice_id                      VARCHAR,
    customer_id                    VARCHAR,
    subscription_id                 VARCHAR,
    project_id                      VARCHAR,
    invoice_date                    DATE,
    due_date                        DATE,
    amount                          NUMBER(15,2),
    tax                              NUMBER(15,2),
    total_amount                    NUMBER(15,2),
    status                          VARCHAR,
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_PAYMENTS (
    payment_id                      VARCHAR,
    invoice_id                      VARCHAR,
    customer_id                    VARCHAR,
    payment_date                    DATE,
    amount_paid                     NUMBER(15,2),
    payment_method                  VARCHAR,
    payment_status                  VARCHAR,
    days_late                       NUMBER(10,0),
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_SUPPORT_TICKETS (
    ticket_id                       VARCHAR,
    customer_id                    VARCHAR,
    agent_id                        VARCHAR,
    category                        VARCHAR,
    priority                        VARCHAR,
    channel                          VARCHAR,
    status                          VARCHAR,
    created_date                   DATE,
    resolution_date                 DATE,
    resolution_time_hours           NUMBER(10,2),
    satisfaction_rating             NUMBER(4,2),
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);

CREATE TABLE IF NOT EXISTS STAGING.STG_CUSTOMER_ACTIVITY (
    activity_id                     VARCHAR,
    customer_id                    VARCHAR,
    activity_date                   DATE,
    activity_type                   VARCHAR,
    duration_minutes                NUMBER(10,2),
    engagement_points               NUMBER(10,2),
    _source_loaded_at              TIMESTAMP_NTZ,
    _staged_at                     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _data_quality_status           VARCHAR(10),
    _data_quality_issue            VARCHAR(2000)
);
