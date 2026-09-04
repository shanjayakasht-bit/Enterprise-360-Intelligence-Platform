-- NEXORA Phase 5: Decision Intelligence Engine output tables.
--
-- These hold the RESULTS of decision_engine/generate_decisions.py -- no
-- computation happens here. Every run does a full refresh (TRUNCATE + bulk
-- insert via the same proven write_table helper from Phases 3/4), safe to
-- rerun idempotently. RAW, STAGING, CORE, and every Phase 2-4 ANALYTICS
-- object are only ever READ by Phase 5 code, never written.
--
-- Run once, before the first pipeline run:
--
--     snowsql -f snowflake/sql/13_decision_engine_tables.sql

USE DATABASE NEXORA_DB;
USE SCHEMA ANALYTICS;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- DI_DECISIONS -- grain: one row per (decision_type, entity_type, entity_id).
-- decision_id IS that composite key (e.g. 'CUSTOMER_RETENTION_CUSTOMER_CUST003241'),
-- so the primary key itself enforces the "no duplicate active decision for
-- identical decision_type+entity_type+entity_id" rule -- see
-- decision_engine/common.py::make_decision_id.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.DI_DECISIONS (
    decision_id                VARCHAR       NOT NULL,
    decision_type                VARCHAR       NOT NULL,  -- CUSTOMER_RETENTION | PROJECT_DELIVERY | PAYMENT_COLLECTION | REVENUE_OPPORTUNITY | SUPPORT_ESCALATION | BUSINESS_ANOMALY
    entity_type                    VARCHAR       NOT NULL,  -- CUSTOMER | PROJECT | INVOICE | REGION | SERVICE | ENTERPRISE
    entity_id                        VARCHAR       NOT NULL,

    title                             VARCHAR       NOT NULL,
    summary                            VARCHAR,

    severity                            VARCHAR       NOT NULL,  -- CRITICAL | HIGH | MEDIUM | LOW
    priority_score                       NUMBER(5,2)   NOT NULL,  -- 0-100, see decision_engine/priority_scoring.py

    what_happened                          VARCHAR       NOT NULL,
    why_it_happened                          VARCHAR       NOT NULL,  -- "Primary contributing signals: ..." -- never phrased as definitive cause
    predicted_outcome                          VARCHAR,               -- NULL when no model-backed prediction applies to this decision

    business_impact_type                         VARCHAR,               -- e.g. ARR_AT_RISK | BUDGET_EXPOSURE | INVOICE_AT_RISK | REVENUE_OPPORTUNITY | REVENUE_DOWNSIDE_RISK
    business_impact_value                          NUMBER(18,2),          -- always >= 0, direction is carried by business_impact_type not sign

    confidence_score                                 NUMBER(5,2),           -- 0-100, derived from the backing models own validated accuracy (see docs/decision_engine.md), never a flat/assumed number

    recommended_action_1                               VARCHAR,
    recommended_action_2                               VARCHAR,
    recommended_action_3                               VARCHAR,
    recommended_action_4                               VARCHAR,
    recommended_action_5                               VARCHAR,

    status                                               VARCHAR       NOT NULL DEFAULT 'NEW',  -- NEW | ACKNOWLEDGED | IN_PROGRESS | RESOLVED | DISMISSED

    generated_at                                           TIMESTAMP_NTZ NOT NULL,

    PRIMARY KEY (decision_id)
);

-- ============================================================
-- DI_EXECUTIVE_SUMMARY -- grain: exactly one row (whole-enterprise snapshot
-- of the current decision backlog), refreshed every run.
-- Every *_at_risk metric is computed from DISTINCT entities (never summed
-- across multiple decisions for the same entity), so a customer with both
-- a CUSTOMER_RETENTION and a BUSINESS_ANOMALY decision contributes its
-- exposure once, not twice -- see decision_engine/generate_decisions.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.DI_EXECUTIVE_SUMMARY (
    critical_decisions                NUMBER(10,0)  NOT NULL,
    high_priority_decisions             NUMBER(10,0)  NOT NULL,
    customers_at_risk                     NUMBER(10,0)  NOT NULL,
    revenue_at_risk                         NUMBER(18,2)  NOT NULL,
    projects_at_risk                          NUMBER(10,0)  NOT NULL,
    payment_value_at_risk                       NUMBER(18,2)  NOT NULL,
    revenue_opportunity_value                     NUMBER(18,2)  NOT NULL,
    generated_at                                    TIMESTAMP_NTZ NOT NULL
);
