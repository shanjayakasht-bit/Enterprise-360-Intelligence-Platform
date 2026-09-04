-- NEXORA Phase 2C: CORE fact table schemas (fact constellation / galaxy
-- schema -- eight fact tables sharing the DIM_CUSTOMER, DIM_EMPLOYEE,
-- DIM_DATE, DIM_SERVICE and DIM_REGION conformed dimensions).
--
-- Every fact's primary key is its own STAGING business identifier (one row
-- per lead/deal/subscription/... exactly matches STAGING's grain) -- no
-- separate fact surrogate key is needed. Foreign surrogate keys default to
-- -1 (Unknown member) rather than NULL when a dimension lookup can't be
-- resolved; see docs/dimensional_model.md. Measures are copied verbatim
-- from STAGING, plus two clearly-derived arithmetic measures (net_deal_value,
-- arr) documented at their column.
--
-- Run after snowflake/sql/06_core_dimensions.sql:
--
--     snowsql -f snowflake/sql/07_core_facts.sql

USE DATABASE NEXORA_DB;
USE SCHEMA CORE;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- FACT_LEADS -- grain: one row per lead (STG_LEADS.lead_id).
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.FACT_LEADS (
    lead_id                    VARCHAR      NOT NULL,
    customer_key               NUMBER(10,0) NOT NULL,
    salesperson_employee_key   NUMBER(10,0) NOT NULL,
    created_date_key           NUMBER(9,0)  NOT NULL,
    converted_date_key         NUMBER(9,0)  NOT NULL, -- -1 (Unknown) when converted_date IS NULL
    lead_source                VARCHAR,               -- degenerate dimension
    status                      VARCHAR,               -- degenerate dimension
    lead_score                 NUMBER(6,2),
    converted_to_deal           BOOLEAN,
    _source_loaded_at          TIMESTAMP_NTZ,
    _core_loaded_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (lead_id)
);

-- ============================================================
-- FACT_DEALS -- grain: one row per deal (STG_DEALS.deal_id).
-- net_deal_value = deal_value * (1 - discount_pct), a derived measure
-- computed purely from two STAGING columns, not an invented figure.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.FACT_DEALS (
    deal_id                    VARCHAR      NOT NULL,
    customer_key               NUMBER(10,0) NOT NULL,
    sales_rep_employee_key     NUMBER(10,0) NOT NULL,
    service_key                NUMBER(10,0) NOT NULL, -- DIM_SERVICE, service_category = 'Product'
    region_key                 NUMBER(10,0) NOT NULL,
    lead_id                    VARCHAR,               -- degenerate: FK to FACT_LEADS.lead_id, no DIM_LEAD requested
    deal_stage                 VARCHAR,               -- degenerate dimension
    segment                     VARCHAR,               -- degenerate dimension
    created_date_key           NUMBER(9,0)  NOT NULL,
    close_date_key              NUMBER(9,0)  NOT NULL, -- -1 (Unknown) when close_date IS NULL
    deal_value                 NUMBER(15,2),
    discount_pct                NUMBER(6,4),
    net_deal_value              NUMBER(15,2),           -- derived: deal_value * (1 - discount_pct)
    is_won                      BOOLEAN,
    _source_loaded_at          TIMESTAMP_NTZ,
    _core_loaded_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (deal_id)
);

-- ============================================================
-- FACT_SUBSCRIPTIONS -- grain: one row per subscription (STG_SUBSCRIPTIONS.subscription_id).
-- arr = mrr * 12, a standard, universally-defined derived measure.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.FACT_SUBSCRIPTIONS (
    subscription_id            VARCHAR      NOT NULL,
    customer_key               NUMBER(10,0) NOT NULL,
    service_key                NUMBER(10,0) NOT NULL, -- DIM_SERVICE, service_category = 'Subscription Plan'
    deal_id                    VARCHAR,               -- degenerate: FK to FACT_DEALS.deal_id, nullable in source
    billing_cycle               VARCHAR,               -- degenerate dimension
    status                      VARCHAR,               -- degenerate dimension
    start_date_key              NUMBER(9,0)  NOT NULL,
    end_date_key                 NUMBER(9,0)  NOT NULL, -- -1 (Unknown) when end_date IS NULL
    mrr                         NUMBER(15,2),
    arr                         NUMBER(15,2),           -- derived: mrr * 12
    auto_renew                  BOOLEAN,
    _source_loaded_at          TIMESTAMP_NTZ,
    _core_loaded_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (subscription_id)
);

-- ============================================================
-- FACT_PROJECTS -- grain: one row per project (STG_PROJECTS.project_id).
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.FACT_PROJECTS (
    project_id                 VARCHAR      NOT NULL,
    customer_key                NUMBER(10,0) NOT NULL,
    project_manager_employee_key NUMBER(10,0) NOT NULL,
    service_key                 NUMBER(10,0) NOT NULL, -- DIM_SERVICE, service_category = 'Project Type'
    deal_id                     VARCHAR,               -- degenerate: FK to FACT_DEALS.deal_id, nullable in source
    status                       VARCHAR,               -- degenerate dimension
    project_risk_category        VARCHAR,               -- degenerate dimension
    start_date_key                NUMBER(9,0)  NOT NULL,
    planned_end_date_key          NUMBER(9,0)  NOT NULL,
    actual_end_date_key           NUMBER(9,0)  NOT NULL, -- -1 (Unknown) when actual_end_date IS NULL
    completion_pct                NUMBER(6,2),
    budget                        NUMBER(15,2),
    actual_cost                   NUMBER(15,2),
    budget_utilization_pct        NUMBER(8,2),
    cost_overrun_pct              NUMBER(8,2),
    project_risk_score            NUMBER(6,2),
    _source_loaded_at            TIMESTAMP_NTZ,
    _core_loaded_at              TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (project_id)
);

-- ============================================================
-- FACT_INVOICES -- grain: one row per invoice (STG_INVOICES.invoice_id).
-- subscription_id / project_id stay as degenerate fact-to-fact references
-- (no DIM_SUBSCRIPTION / DIM_PROJECT was requested); both are legitimately
-- nullable (a standalone invoice, per Phase 1/2B).
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.FACT_INVOICES (
    invoice_id                  VARCHAR      NOT NULL,
    customer_key                 NUMBER(10,0) NOT NULL,
    subscription_id              VARCHAR,
    project_id                   VARCHAR,
    status                        VARCHAR,               -- degenerate dimension
    invoice_date_key              NUMBER(9,0)  NOT NULL,
    due_date_key                  NUMBER(9,0)  NOT NULL,
    amount                        NUMBER(15,2),
    tax                           NUMBER(15,2),
    total_amount                  NUMBER(15,2),
    _source_loaded_at            TIMESTAMP_NTZ,
    _core_loaded_at              TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (invoice_id)
);

-- ============================================================
-- FACT_PAYMENTS -- grain: one row per payment (STG_PAYMENTS.payment_id).
-- invoice_id stays a degenerate fact-to-fact reference to FACT_INVOICES.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.FACT_PAYMENTS (
    payment_id                  VARCHAR      NOT NULL,
    invoice_id                   VARCHAR      NOT NULL,
    customer_key                 NUMBER(10,0) NOT NULL,
    payment_date_key              NUMBER(9,0)  NOT NULL,
    payment_method                VARCHAR,               -- degenerate dimension
    payment_status                 VARCHAR,               -- degenerate dimension
    amount_paid                    NUMBER(15,2),
    days_late                      NUMBER(10,0),
    _source_loaded_at             TIMESTAMP_NTZ,
    _core_loaded_at               TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (payment_id)
);

-- ============================================================
-- FACT_SUPPORT -- grain: one row per support ticket (STG_SUPPORT_TICKETS.ticket_id).
-- No SLA measures are modeled: STAGING/Phase 1 define no SLA target or
-- policy field, so an SLA-hours/SLA-breach measure would be invented
-- rather than sourced -- see docs/dimensional_model.md.
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.FACT_SUPPORT (
    ticket_id                    VARCHAR      NOT NULL,
    customer_key                  NUMBER(10,0) NOT NULL,
    agent_employee_key             NUMBER(10,0) NOT NULL,
    category                       VARCHAR,               -- degenerate dimension
    priority                        VARCHAR,               -- degenerate dimension
    channel                         VARCHAR,               -- degenerate dimension
    status                          VARCHAR,               -- degenerate dimension
    created_date_key                NUMBER(9,0)  NOT NULL,
    resolution_date_key             NUMBER(9,0)  NOT NULL, -- -1 (Unknown) when resolution_date IS NULL
    resolution_time_hours           NUMBER(10,2),
    satisfaction_rating             NUMBER(4,2),
    _source_loaded_at               TIMESTAMP_NTZ,
    _core_loaded_at                 TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (ticket_id)
);

-- ============================================================
-- FACT_CUSTOMER_ACTIVITY -- grain: one row per customer activity event
-- (STG_CUSTOMER_ACTIVITY.activity_id).
-- ============================================================
CREATE TABLE IF NOT EXISTS CORE.FACT_CUSTOMER_ACTIVITY (
    activity_id                  VARCHAR      NOT NULL,
    customer_key                  NUMBER(10,0) NOT NULL,
    activity_date_key             NUMBER(9,0)  NOT NULL,
    activity_type                 VARCHAR,               -- degenerate dimension
    duration_minutes               NUMBER(10,2),
    engagement_points               NUMBER(10,2),
    _source_loaded_at              TIMESTAMP_NTZ,
    _core_loaded_at                TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (activity_id)
);
