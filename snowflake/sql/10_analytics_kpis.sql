-- NEXORA Phase 2D: ANALYTICS.VW_EXECUTIVE_OVERVIEW -- the one-row executive
-- KPI view, including the Enterprise Health Score. Reads only from
-- NEXORA_DB.CORE, same as every view in 09_analytics_views.sql.
--
-- KPI definitions (full detail in docs/analytics_layer.md):
--   total_revenue            = SUM(FACT_DEALS.net_deal_value) WHERE is_won  -- won deal bookings
--   active_customers         = COUNT(DISTINCT customer_key) with >=1 Active subscription
--   active_subscriptions     = COUNT(FACT_SUBSCRIPTIONS) WHERE status = 'Active'
--   active_projects          = COUNT(FACT_PROJECTS) WHERE status NOT IN ('Completed','Cancelled')
--   projects_at_risk         = active_projects AND project_risk_category IN ('High','Critical')
--   open_support_tickets     = COUNT(FACT_SUPPORT) WHERE status IN ('Open','In Progress','Escalated')
--   support_sla_percentage   = % of RESOLVED tickets resolved within their priority's SLA target
--                               (SLA thresholds are an ANALYTICS-layer assumption -- see
--                               09_analytics_views.sql's file header and docs/analytics_layer.md)
--   average_customer_health  = AVG(100 - churn_risk_score) over current customers
--   total_invoice_amount     = SUM(FACT_INVOICES.total_amount)                  -- billed
--   total_payments_received  = SUM(FACT_PAYMENTS.amount_paid)                   -- collected
--   outstanding_amount       = total_invoice_amount - total_payments_received
-- total_revenue, total_invoice_amount and total_payments_received are three
-- DIFFERENT lifecycle stages (sold / billed / collected) -- never add them
-- together.
--
-- Run after snowflake/sql/09_analytics_views.sql:
--
--     snowsql -f snowflake/sql/10_analytics_kpis.sql

USE DATABASE NEXORA_DB;
USE SCHEMA ANALYTICS;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- VW_EXECUTIVE_OVERVIEW -- grain: exactly one row (whole-enterprise snapshot).
--
-- Enterprise Health Score: a transparent weighted blend of five documented
-- components, weights summing to 100%:
--   25% customer_health_component  = AVG(100 - churn_risk_score), current customers
--   25% financial_health_component = 100 * payments_received / invoice_total, capped at 100
--   20% project_health_component   = AVG(100 - project_risk_score), all projects
--   20% support_sla_component      = support_sla_percentage (resolved tickets only)
--   10% revenue_trend_component    = 50 (flat) +/- 100 * QoQ%% change in invoiced revenue
--                                     over the most recent 90 vs prior 90 days of DATA
--                                     actually present (anchored to MAX(invoice_date), not
--                                     live CURRENT_DATE), capped to [0,100]
-- If any component cannot be computed (e.g. NULL because there is no prior-period
-- revenue to compare against), its weight is transparently redistributed: both
-- the weighted numerator and the weight denominator drop that component's
-- contribution together, so the remaining components' weights are rescaled to
-- still sum to 100% of what's left, rather than treating a missing component as 0.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_EXECUTIVE_OVERVIEW AS
WITH deal_metrics AS (
    SELECT SUM(IFF(is_won, net_deal_value, 0)) AS total_revenue
    FROM CORE.FACT_DEALS
),
subscription_metrics AS (
    SELECT COUNT(DISTINCT customer_key) AS active_customers,
           COUNT(*) AS active_subscriptions
    FROM CORE.FACT_SUBSCRIPTIONS WHERE status = 'Active'
),
project_metrics AS (
    SELECT
        SUM(IFF(status NOT IN ('Completed', 'Cancelled'), 1, 0)) AS active_projects,
        SUM(IFF(status NOT IN ('Completed', 'Cancelled') AND project_risk_category IN ('High', 'Critical'), 1, 0)) AS projects_at_risk,
        AVG(100 - project_risk_score) AS project_health
    FROM CORE.FACT_PROJECTS
),
support_metrics AS (
    SELECT
        SUM(IFF(status IN ('Open', 'In Progress', 'Escalated'), 1, 0)) AS open_support_tickets,
        100.0 * SUM(IFF(
                resolution_time_hours IS NOT NULL
                AND resolution_time_hours <= CASE priority
                        WHEN 'Critical' THEN 12 WHEN 'High' THEN 48
                        WHEN 'Medium' THEN 120 WHEN 'Low' THEN 240 ELSE 240 END,
                1, 0))
            / NULLIF(SUM(IFF(resolution_time_hours IS NOT NULL, 1, 0)), 0) AS support_sla_percentage
    FROM CORE.FACT_SUPPORT
),
customer_metrics AS (
    SELECT AVG(100 - churn_risk_score) AS average_customer_health
    FROM CORE.DIM_CUSTOMER WHERE is_current = TRUE AND customer_key <> -1
),
finance_metrics AS (
    SELECT SUM(total_amount) AS total_invoice_amount FROM CORE.FACT_INVOICES
),
payment_metrics AS (
    SELECT SUM(amount_paid) AS total_payments_received FROM CORE.FACT_PAYMENTS
),
revenue_window AS (
    SELECT
        SUM(IFF(dt.full_date > anchor.latest_date - 90, i.total_amount, 0)) AS recent_90d,
        SUM(IFF(dt.full_date <= anchor.latest_date - 90 AND dt.full_date > anchor.latest_date - 180, i.total_amount, 0)) AS prior_90d
    FROM CORE.FACT_INVOICES i
    JOIN CORE.DIM_DATE dt ON dt.date_key = i.invoice_date_key
    CROSS JOIN (
        SELECT MAX(dt2.full_date) AS latest_date
        FROM CORE.FACT_INVOICES i2 JOIN CORE.DIM_DATE dt2 ON dt2.date_key = i2.invoice_date_key
    ) anchor
),
components AS (
    SELECT
        dm.total_revenue,
        sm.active_customers, sm.active_subscriptions,
        prm.active_projects, prm.projects_at_risk, prm.project_health,
        spm.open_support_tickets, spm.support_sla_percentage,
        cm.average_customer_health,
        fm.total_invoice_amount,
        pm.total_payments_received,
        LEAST(100, 100.0 * pm.total_payments_received / NULLIF(fm.total_invoice_amount, 0)) AS financial_health,
        CASE WHEN rw.prior_90d IS NULL OR rw.prior_90d = 0 THEN NULL
             ELSE LEAST(100, GREATEST(0, 50 + 100.0 * (rw.recent_90d - rw.prior_90d) / rw.prior_90d))
        END AS revenue_trend
    FROM deal_metrics dm
    CROSS JOIN subscription_metrics sm
    CROSS JOIN project_metrics prm
    CROSS JOIN support_metrics spm
    CROSS JOIN customer_metrics cm
    CROSS JOIN finance_metrics fm
    CROSS JOIN payment_metrics pm
    CROSS JOIN revenue_window rw
)
SELECT
    total_revenue,
    active_customers,
    active_subscriptions,
    active_projects,
    projects_at_risk,
    open_support_tickets,
    ROUND(support_sla_percentage, 1)                       AS support_sla_percentage,
    ROUND(average_customer_health, 1)                       AS average_customer_health,
    total_invoice_amount,
    total_payments_received,
    (total_invoice_amount - total_payments_received)        AS outstanding_amount,

    ROUND(average_customer_health, 1)                       AS customer_health_component,
    ROUND(financial_health, 1)                               AS financial_health_component,
    ROUND(project_health, 1)                                 AS project_health_component,
    ROUND(support_sla_percentage, 1)                         AS support_sla_component,
    ROUND(revenue_trend, 1)                                  AS revenue_trend_component,

    ROUND(
        (COALESCE(average_customer_health, 0) * 25
       + COALESCE(financial_health, 0) * 25
       + COALESCE(project_health, 0) * 20
       + COALESCE(support_sla_percentage, 0) * 20
       + COALESCE(revenue_trend, 0) * 10)
        / NULLIF(
              IFF(average_customer_health IS NULL, 0, 25)
            + IFF(financial_health IS NULL, 0, 25)
            + IFF(project_health IS NULL, 0, 20)
            + IFF(support_sla_percentage IS NULL, 0, 20)
            + IFF(revenue_trend IS NULL, 0, 10)
          , 0)
    , 1)                                                     AS enterprise_health_score
FROM components;
