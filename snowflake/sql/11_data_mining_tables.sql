-- NEXORA Phase 3: data mining output tables.
--
-- These hold the RESULTS of the Python mining pipelines in mining/ --
-- nothing here computes anything itself. Every pipeline does a full
-- refresh (TRUNCATE + bulk insert via mining/common.py's write_table),
-- which is safe to rerun idempotently: reruns replace the same rows
-- rather than duplicating them. CORE and ANALYTICS source objects are
-- never written to by any Phase 3 script.
--
-- Run once, before the first pipeline run:
--
--     snowsql -f snowflake/sql/11_data_mining_tables.sql

USE DATABASE NEXORA_DB;
USE SCHEMA ANALYTICS;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- DM_CUSTOMER_SEGMENTS -- grain: one row per clustered customer.
-- Source: mining/customer_segmentation.py, from ANALYTICS.VW_CUSTOMER_360.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.DM_CUSTOMER_SEGMENTS (
    customer_id                VARCHAR      NOT NULL,
    cluster_id                 NUMBER(4,0)  NOT NULL,
    segment_name                VARCHAR      NOT NULL,
    distance_from_centroid      NUMBER(12,6),
    generated_at                TIMESTAMP_NTZ NOT NULL,
    PRIMARY KEY (customer_id)
);

-- ============================================================
-- DM_CUSTOMER_CLUSTER_PROFILE -- grain: one row per cluster.
-- Cluster-level average of every raw (unscaled) feature used for
-- clustering, plus the run's overall model-quality metrics repeated on
-- every row for self-containment (selected_k, silhouette_score).
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.DM_CUSTOMER_CLUSTER_PROFILE (
    cluster_id                      NUMBER(4,0)  NOT NULL,
    segment_name                     VARCHAR      NOT NULL,
    customer_count                   NUMBER(10,0),
    avg_total_revenue                NUMBER(15,2),
    avg_arr                          NUMBER(15,2),
    avg_active_subscriptions          NUMBER(10,2),
    avg_usage_score                   NUMBER(6,2),
    avg_support_ticket_count          NUMBER(10,2),
    avg_sla_breaches                  NUMBER(10,2),
    avg_support_satisfaction          NUMBER(6,2),
    avg_payment_delay                 NUMBER(10,2),
    avg_outstanding_amount            NUMBER(15,2),
    avg_project_risk                  NUMBER(6,2),
    avg_customer_health_score         NUMBER(6,2),
    selected_k                        NUMBER(4,0),
    silhouette_score                   NUMBER(6,4),
    generated_at                       TIMESTAMP_NTZ NOT NULL,
    PRIMARY KEY (cluster_id)
);

-- ============================================================
-- DM_SERVICE_ASSOCIATIONS -- grain: one row per (antecedent, consequent)
-- association rule that survived the configured support/confidence/lift
-- thresholds (see docs/data_mining.md).
-- Source: mining/association_rules.py, from CORE.FACT_DEALS /
-- FACT_SUBSCRIPTIONS / FACT_PROJECTS via DIM_SERVICE.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.DM_SERVICE_ASSOCIATIONS (
    antecedent           VARCHAR       NOT NULL,
    consequent           VARCHAR       NOT NULL,
    support              NUMBER(8,6),
    confidence           NUMBER(8,6),
    lift                  NUMBER(10,4),
    transaction_count     NUMBER(10,0),
    generated_at          TIMESTAMP_NTZ NOT NULL
);

-- ============================================================
-- DM_BUSINESS_ANOMALIES -- grain: one row per (entity_type, entity_id,
-- anomaly_type) scored record.
-- Source: mining/anomaly_detection.py, Isolation Forest over
-- customer-level and time-aggregated business features from
-- ANALYTICS/CORE.
-- ============================================================
CREATE TABLE IF NOT EXISTS ANALYTICS.DM_BUSINESS_ANOMALIES (
    entity_type           VARCHAR       NOT NULL,  -- e.g. 'CUSTOMER', 'MONTH'
    entity_id              VARCHAR       NOT NULL,  -- e.g. customer_id, 'YYYY-MM'
    anomaly_type            VARCHAR       NOT NULL,  -- which feature set was scored
    anomaly_score            NUMBER(10,6),            -- Isolation Forest decision_function score (lower = more anomalous)
    is_anomaly               BOOLEAN,
    observed_value            VARCHAR,                 -- the feature(s) that deviated most, with their actual values
    expected_context          VARCHAR,                 -- population median/typical-range context for those same features
    generated_at              TIMESTAMP_NTZ NOT NULL,
    PRIMARY KEY (entity_type, entity_id, anomaly_type)
);
