-- NEXORA Phase 2D: ANALYTICS detail views.
--
-- Every view below reads ONLY from NEXORA_DB.CORE (dimensions/facts) --
-- never RAW or STAGING. Each view is fully self-contained (queries CORE
-- directly, no view-on-view dependencies) so any one of them can be
-- recreated independently, in any order.
--
-- Conventions used throughout (see docs/analytics_layer.md for the full
-- writeup):
--   * "Revenue" (unqualified) always means WON deal value
--     (SUM(net_deal_value) WHERE is_won = TRUE) -- the sales-bookings
--     definition. Billed amounts are always called invoice_amount /
--     invoice_total; collected cash is always payments_received; recurring
--     commitment is always mrr/arr. These four are related stages of the
--     same lifecycle, never summed together into one number.
--   * Every fact is pre-aggregated to the target grain in its own CTE
--     BEFORE being joined to anything else, specifically to prevent
--     fan-out double counting (joining two "many" facts directly on a
--     shared key multiplies rows and inflates SUMs -- see
--     VW_FINANCE_SUMMARY and VW_CUSTOMER_360 for the clearest examples).
--   * Dimension joins use is_current = TRUE (current SCD2 version) and
--     exclude the -1 Unknown member when listing real business entities.
--   * SLA policy (VW_SUPPORT_HEALTH): NEXORA's Phase 1 source data defines
--     no SLA target field anywhere (checked before Phase 2C's FACT_SUPPORT
--     design, and again here) -- these thresholds are an explicit
--     ANALYTICS-layer assumption, not a sourced business rule:
--       Critical -> 12 hours, High -> 48 hours, Medium -> 120 hours, Low -> 240 hours
--     (chosen after checking this dataset's own resolution-time percentiles --
--     see docs/analytics_layer.md -- not arbitrary round numbers).
--     Documented prominently in docs/analytics_layer.md as a placeholder
--     pending real policy input; the exact same CASE expression is reused
--     verbatim everywhere SLA is computed, so it never drifts.
--   * REFERENCE_DATE: any "as of today" calculation (e.g. days_to_deadline)
--     uses the literal 2026-09-04, mirroring config.settings.REFERENCE_DATE
--     from Phase 1, so a project's "days to deadline" stays consistent with
--     the same fixed "today" the rest of the warehouse (e.g.
--     DIM_CUSTOMER.days_to_renewal) was computed against, instead of
--     silently drifting a day further every time this view is queried.
--
-- Run after snowflake/sql/08_core_load.sql:
--
--     snowsql -f snowflake/sql/09_analytics_views.sql

USE DATABASE NEXORA_DB;
USE SCHEMA ANALYTICS;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- VW_SUPPORT_HEALTH -- grain: one row per support ticket.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_SUPPORT_HEALTH AS
SELECT
    t.ticket_id,
    cust.customer_id,
    cust.company_name,
    agent.employee_id                              AS agent_employee_id,
    agent.full_name                                 AS agent_name,
    t.category,
    t.priority,
    t.channel,
    t.status,
    created.full_date                               AS created_date,
    resolved.full_date                               AS resolution_date,
    t.resolution_time_hours,
    t.satisfaction_rating,
    -- ANALYTICS-layer SLA policy assumption -- see file header comment.
    CASE t.priority
        WHEN 'Critical' THEN 12
        WHEN 'High'     THEN 48
        WHEN 'Medium'   THEN 120
        WHEN 'Low'      THEN 240
        ELSE 240
    END                                              AS sla_target_hours,
    CASE
        WHEN t.resolution_time_hours IS NOT NULL THEN
            IFF(t.resolution_time_hours > CASE t.priority
                    WHEN 'Critical' THEN 12 WHEN 'High' THEN 48
                    WHEN 'Medium' THEN 120 WHEN 'Low' THEN 240 ELSE 240 END,
                TRUE, FALSE)
        ELSE
            -- still open: breached if already past its SLA window since creation
            IFF(DATEDIFF('hour', created.full_date, '2026-09-04'::TIMESTAMP_NTZ) >
                    CASE t.priority
                        WHEN 'Critical' THEN 12 WHEN 'High' THEN 48
                        WHEN 'Medium' THEN 120 WHEN 'Low' THEN 240 ELSE 240 END,
                TRUE, FALSE)
    END                                              AS sla_breach
FROM CORE.FACT_SUPPORT t
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_key = t.customer_key
LEFT JOIN CORE.DIM_EMPLOYEE agent ON agent.employee_key = t.agent_employee_key
LEFT JOIN CORE.DIM_DATE created ON created.date_key = t.created_date_key
LEFT JOIN CORE.DIM_DATE resolved ON resolved.date_key = t.resolution_date_key;

-- ============================================================
-- VW_PROJECT_RISK -- grain: one row per project.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_PROJECT_RISK AS
SELECT
    p.project_id,
    cust.customer_id,
    cust.company_name,
    dept.department_name,
    pm.employee_id                                  AS project_manager_id,
    pm.full_name                                    AS project_manager_name,
    p.status,
    p.budget,
    p.actual_cost,
    (p.actual_cost - p.budget)                       AS cost_variance,        -- derived: positive = over budget
    p.budget_utilization_pct,
    p.cost_overrun_pct,
    p.completion_pct,
    p.project_risk_score,
    p.project_risk_category,
    planned.full_date                                AS planned_end_date,
    -- REFERENCE_DATE = 2026-09-04, mirrors config.settings.REFERENCE_DATE (Phase 1) -- see file header.
    DATEDIFF('day', '2026-09-04'::DATE, planned.full_date) AS days_to_deadline  -- negative = overdue
FROM CORE.FACT_PROJECTS p
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_key = p.customer_key
LEFT JOIN CORE.DIM_EMPLOYEE pm ON pm.employee_key = p.project_manager_employee_key
LEFT JOIN CORE.DIM_DEPARTMENT dept ON dept.department_key = pm.department_key
LEFT JOIN CORE.DIM_DATE planned ON planned.date_key = p.planned_end_date_key;

-- ============================================================
-- VW_FINANCE_SUMMARY -- grain: one row per invoice.
-- Payments are pre-aggregated PER INVOICE in their own CTE before being
-- joined, specifically so an invoice with multiple/partial payments does
-- not fan out and inflate invoice-level totals.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_FINANCE_SUMMARY AS
WITH payments_by_invoice AS (
    SELECT
        invoice_id,
        SUM(amount_paid) AS payments_received,
        AVG(days_late)    AS avg_payment_delay_days,
        COUNT(*)          AS payment_count
    FROM CORE.FACT_PAYMENTS
    GROUP BY invoice_id
)
SELECT
    i.invoice_id,
    cust.customer_id,
    cust.company_name,
    reg.region_name,
    inv_date.full_date                              AS invoice_date,
    due_date.full_date                               AS due_date,
    i.status,
    i.amount,
    i.tax,
    i.total_amount,
    COALESCE(pbi.payments_received, 0)                AS payments_received,
    (i.total_amount - COALESCE(pbi.payments_received, 0)) AS outstanding_amount,
    pbi.avg_payment_delay_days,
    COALESCE(pbi.payment_count, 0)                    AS payment_count
FROM CORE.FACT_INVOICES i
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_key = i.customer_key
LEFT JOIN CORE.DIM_REGION reg ON reg.region_key = cust.region_key
LEFT JOIN CORE.DIM_DATE inv_date ON inv_date.date_key = i.invoice_date_key
LEFT JOIN CORE.DIM_DATE due_date ON due_date.date_key = i.due_date_key
LEFT JOIN payments_by_invoice pbi ON pbi.invoice_id = i.invoice_id;

-- ============================================================
-- VW_REVENUE_TRENDS -- grain: one row per (date, region, segment).
-- Deliberately NOT broken out by service here: only FACT_DEALS and
-- FACT_SUBSCRIPTIONS carry a service_key -- FACT_INVOICES/FACT_PAYMENTS do
-- not (subscription_id/project_id on an invoice are optional degenerate
-- references, not a service dimension). Service-level revenue lives in
-- VW_SERVICE_PERFORMANCE instead of forcing a fake service grain here.
--
-- Each of the four metric columns is independently pre-aggregated to this
-- grain in its own CTE, then LEFT JOINed onto a UNION'd grain spine --
-- never summed against each other (see the revenue-definition note in the
-- file header: these are four different lifecycle stages, not four parts
-- of one number).
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_REVENUE_TRENDS AS
WITH deal_revenue AS (
    SELECT dt.full_date, dt.year, dt.quarter, dt.month_number, dt.month_name,
           r.region_name, d.segment,
           SUM(d.net_deal_value) AS deal_revenue
    FROM CORE.FACT_DEALS d
    JOIN CORE.DIM_DATE dt ON dt.date_key = d.close_date_key
    JOIN CORE.DIM_REGION r ON r.region_key = d.region_key
    WHERE d.is_won = TRUE
    GROUP BY dt.full_date, dt.year, dt.quarter, dt.month_number, dt.month_name, r.region_name, d.segment
),
subscription_revenue AS (
    SELECT dt.full_date, dt.year, dt.quarter, dt.month_number, dt.month_name,
           r.region_name, c.segment,
           SUM(s.mrr) AS subscription_mrr_booked,
           SUM(s.arr) AS subscription_arr_booked
    FROM CORE.FACT_SUBSCRIPTIONS s
    JOIN CORE.DIM_DATE dt ON dt.date_key = s.start_date_key
    JOIN CORE.DIM_CUSTOMER c ON c.customer_key = s.customer_key
    JOIN CORE.DIM_REGION r ON r.region_key = c.region_key
    GROUP BY dt.full_date, dt.year, dt.quarter, dt.month_number, dt.month_name, r.region_name, c.segment
),
invoice_revenue AS (
    SELECT dt.full_date, dt.year, dt.quarter, dt.month_number, dt.month_name,
           r.region_name, c.segment,
           SUM(i.total_amount) AS invoice_amount
    FROM CORE.FACT_INVOICES i
    JOIN CORE.DIM_DATE dt ON dt.date_key = i.invoice_date_key
    JOIN CORE.DIM_CUSTOMER c ON c.customer_key = i.customer_key
    JOIN CORE.DIM_REGION r ON r.region_key = c.region_key
    GROUP BY dt.full_date, dt.year, dt.quarter, dt.month_number, dt.month_name, r.region_name, c.segment
),
payment_revenue AS (
    SELECT dt.full_date, dt.year, dt.quarter, dt.month_number, dt.month_name,
           r.region_name, c.segment,
           SUM(p.amount_paid) AS payments_received
    FROM CORE.FACT_PAYMENTS p
    JOIN CORE.DIM_DATE dt ON dt.date_key = p.payment_date_key
    JOIN CORE.DIM_CUSTOMER c ON c.customer_key = p.customer_key
    JOIN CORE.DIM_REGION r ON r.region_key = c.region_key
    GROUP BY dt.full_date, dt.year, dt.quarter, dt.month_number, dt.month_name, r.region_name, c.segment
),
grain_spine AS (
    SELECT full_date, year, quarter, month_number, month_name, region_name, segment FROM deal_revenue
    UNION
    SELECT full_date, year, quarter, month_number, month_name, region_name, segment FROM subscription_revenue
    UNION
    SELECT full_date, year, quarter, month_number, month_name, region_name, segment FROM invoice_revenue
    UNION
    SELECT full_date, year, quarter, month_number, month_name, region_name, segment FROM payment_revenue
)
SELECT
    gs.full_date, gs.year, gs.quarter, gs.month_number, gs.month_name, gs.region_name, gs.segment,
    COALESCE(dr.deal_revenue, 0)              AS deal_revenue,
    COALESCE(sr.subscription_mrr_booked, 0)   AS subscription_mrr_booked,
    COALESCE(sr.subscription_arr_booked, 0)   AS subscription_arr_booked,
    COALESCE(ir.invoice_amount, 0)            AS invoice_amount,
    COALESCE(pr.payments_received, 0)         AS payments_received
FROM grain_spine gs
LEFT JOIN deal_revenue dr
    ON dr.full_date = gs.full_date AND dr.region_name = gs.region_name AND dr.segment = gs.segment
LEFT JOIN subscription_revenue sr
    ON sr.full_date = gs.full_date AND sr.region_name = gs.region_name AND sr.segment = gs.segment
LEFT JOIN invoice_revenue ir
    ON ir.full_date = gs.full_date AND ir.region_name = gs.region_name AND ir.segment = gs.segment
LEFT JOIN payment_revenue pr
    ON pr.full_date = gs.full_date AND pr.region_name = gs.region_name AND pr.segment = gs.segment;

-- ============================================================
-- VW_CUSTOMER_HEALTH -- grain: one row per current customer.
-- health_score reuses Phase 1's own validated churn_risk_score formula,
-- inverted (100 - churn_risk_score) -- not a new invented score. See
-- docs/analytics_layer.md.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_CUSTOMER_HEALTH AS
WITH open_tickets AS (
    SELECT customer_key, COUNT(*) AS open_ticket_count
    FROM CORE.FACT_SUPPORT
    WHERE status IN ('Open', 'In Progress', 'Escalated')
    GROUP BY customer_key
),
finance AS (
    SELECT
        i.customer_key,
        SUM(i.total_amount) AS invoice_total,
        SUM(COALESCE(pay.amount_paid, 0)) AS payments_received
    FROM CORE.FACT_INVOICES i
    LEFT JOIN (SELECT invoice_id, SUM(amount_paid) AS amount_paid FROM CORE.FACT_PAYMENTS GROUP BY invoice_id) pay
        ON pay.invoice_id = i.invoice_id
    GROUP BY i.customer_key
)
SELECT
    c.customer_id,
    c.company_name,
    c.segment,
    reg.region_name,
    (100 - c.churn_risk_score)                       AS health_score,
    c.churn_risk_score,
    c.churn_risk_category,
    CASE c.churn_risk_category
        WHEN 'Low'      THEN 'Healthy'
        WHEN 'Medium'   THEN 'Watch'
        WHEN 'High'     THEN 'At Risk'
        WHEN 'Critical' THEN 'Critical'
        ELSE 'Unknown'
    END                                                AS risk_classification,
    c.product_usage_score,
    c.engagement_score,
    c.satisfaction_score,
    c.support_ticket_count_recent,
    COALESCE(ot.open_ticket_count, 0)                  AS open_ticket_count,
    c.avg_payment_delay_days,
    (fin.invoice_total - fin.payments_received)         AS outstanding_amount,
    c.renewal_date,
    c.days_to_renewal
FROM CORE.DIM_CUSTOMER c
LEFT JOIN CORE.DIM_REGION reg ON reg.region_key = c.region_key
LEFT JOIN open_tickets ot ON ot.customer_key = c.customer_key
LEFT JOIN finance fin ON fin.customer_key = c.customer_key
WHERE c.is_current = TRUE AND c.customer_key <> -1;

-- ============================================================
-- VW_CUSTOMER_360 -- grain: one row per current customer.
-- Every fact is pre-aggregated to one row per customer_key in its own CTE
-- before joining -- this is the view most exposed to fan-out risk (7
-- different facts touch "customer"), so each is aggregated independently.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_CUSTOMER_360 AS
WITH deals_agg AS (
    SELECT customer_key,
           SUM(deal_value) AS total_deal_value,
           SUM(IFF(is_won, deal_value, 0)) AS won_deal_value,
           SUM(IFF(is_won, net_deal_value, 0)) AS revenue
    FROM CORE.FACT_DEALS GROUP BY customer_key
),
subs_agg AS (
    SELECT customer_key,
           COUNT(*) AS active_subscriptions,
           SUM(arr) AS arr,
           SUM(mrr) AS mrr
    FROM CORE.FACT_SUBSCRIPTIONS WHERE status = 'Active' GROUP BY customer_key
),
projects_agg AS (
    SELECT customer_key,
           COUNT(*) AS project_count,
           SUM(IFF(status = 'Delayed', 1, 0)) AS delayed_projects,
           AVG(project_risk_score) AS project_risk
    FROM CORE.FACT_PROJECTS GROUP BY customer_key
),
invoices_agg AS (
    SELECT customer_key, SUM(total_amount) AS invoice_total
    FROM CORE.FACT_INVOICES GROUP BY customer_key
),
payments_agg AS (
    SELECT customer_key,
           SUM(amount_paid) AS payments_received,
           AVG(days_late) AS average_payment_delay
    FROM CORE.FACT_PAYMENTS GROUP BY customer_key
),
support_agg AS (
    SELECT
        customer_key,
        COUNT(*) AS support_ticket_count,
        SUM(IFF(status IN ('Open','In Progress','Escalated'), 1, 0)) AS open_ticket_count,
        -- SLA policy: identical thresholds to VW_SUPPORT_HEALTH -- see file header.
        SUM(IFF(
            resolution_time_hours IS NOT NULL
            AND resolution_time_hours > CASE priority
                    WHEN 'Critical' THEN 12 WHEN 'High' THEN 48
                    WHEN 'Medium' THEN 120 WHEN 'Low' THEN 240 ELSE 240 END,
            1, 0)) AS sla_breaches,
        AVG(satisfaction_rating) AS average_support_satisfaction
    FROM CORE.FACT_SUPPORT GROUP BY customer_key
),
activity_agg AS (
    SELECT a.customer_key,
           COUNT(*) AS activity_count,
           MAX(dt.full_date) AS recent_activity_date
    FROM CORE.FACT_CUSTOMER_ACTIVITY a
    LEFT JOIN CORE.DIM_DATE dt ON dt.date_key = a.activity_date_key
    GROUP BY a.customer_key
)
SELECT
    c.customer_id,
    c.company_name,
    c.segment,
    reg.region_name                                    AS region,
    c.industry,

    COALESCE(d.total_deal_value, 0)                     AS total_deal_value,
    COALESCE(d.won_deal_value, 0)                       AS won_deal_value,
    COALESCE(d.revenue, 0)                               AS total_revenue,       -- won net deal value, see file header
    COALESCE(s.active_subscriptions, 0)                  AS active_subscriptions,
    COALESCE(s.arr, 0)                                   AS arr,
    COALESCE(s.mrr, 0)                                   AS mrr,

    COALESCE(p.project_count, 0)                         AS project_count,
    COALESCE(p.delayed_projects, 0)                      AS delayed_projects,
    p.project_risk,

    COALESCE(inv.invoice_total, 0)                       AS invoice_total,
    COALESCE(pay.payments_received, 0)                   AS payments_received,
    (COALESCE(inv.invoice_total, 0) - COALESCE(pay.payments_received, 0)) AS outstanding_amount,
    pay.average_payment_delay,

    COALESCE(sup.support_ticket_count, 0)                AS support_ticket_count,
    COALESCE(sup.open_ticket_count, 0)                   AS open_ticket_count,
    COALESCE(sup.sla_breaches, 0)                        AS sla_breaches,
    sup.average_support_satisfaction,

    COALESCE(act.activity_count, 0)                      AS activity_count,
    c.product_usage_score                                 AS average_usage_score,
    act.recent_activity_date,

    (100 - c.churn_risk_score)                            AS customer_health_score,
    CASE c.churn_risk_category
        WHEN 'Low'      THEN 'Healthy'
        WHEN 'Medium'   THEN 'Watch'
        WHEN 'High'     THEN 'At Risk'
        WHEN 'Critical' THEN 'Critical'
        ELSE 'Unknown'
    END                                                    AS customer_status
FROM CORE.DIM_CUSTOMER c
LEFT JOIN CORE.DIM_REGION reg ON reg.region_key = c.region_key
LEFT JOIN deals_agg d ON d.customer_key = c.customer_key
LEFT JOIN subs_agg s ON s.customer_key = c.customer_key
LEFT JOIN projects_agg p ON p.customer_key = c.customer_key
LEFT JOIN invoices_agg inv ON inv.customer_key = c.customer_key
LEFT JOIN payments_agg pay ON pay.customer_key = c.customer_key
LEFT JOIN support_agg sup ON sup.customer_key = c.customer_key
LEFT JOIN activity_agg act ON act.customer_key = c.customer_key
WHERE c.is_current = TRUE AND c.customer_key <> -1;

-- ============================================================
-- VW_REGION_PERFORMANCE -- grain: one row per region.
-- Each metric is independently aggregated from its own fact table (no two
-- "many" facts are ever joined to each other here), so no fan-out risk.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_REGION_PERFORMANCE AS
WITH customers_by_region AS (
    SELECT region_key, COUNT(*) AS customer_count, AVG(100 - churn_risk_score) AS average_health_score
    FROM CORE.DIM_CUSTOMER WHERE is_current = TRUE AND customer_key <> -1
    GROUP BY region_key
),
revenue_by_region AS (
    SELECT region_key, SUM(net_deal_value) AS revenue, COUNT(*) AS deal_count
    FROM CORE.FACT_DEALS WHERE is_won = TRUE
    GROUP BY region_key
),
projects_by_region AS (
    SELECT c.region_key, COUNT(*) AS project_count
    FROM CORE.FACT_PROJECTS p
    JOIN CORE.DIM_CUSTOMER c ON c.customer_key = p.customer_key
    GROUP BY c.region_key
),
support_by_region AS (
    SELECT c.region_key, COUNT(*) AS support_load
    FROM CORE.FACT_SUPPORT t
    JOIN CORE.DIM_CUSTOMER c ON c.customer_key = t.customer_key
    GROUP BY c.region_key
)
SELECT
    r.region_name,
    COALESCE(cbr.customer_count, 0)     AS customer_count,
    COALESCE(rbr.revenue, 0)            AS revenue,
    COALESCE(rbr.deal_count, 0)         AS deal_count,
    COALESCE(pbr.project_count, 0)      AS project_count,
    COALESCE(sbr.support_load, 0)       AS support_load,
    cbr.average_health_score
FROM CORE.DIM_REGION r
LEFT JOIN customers_by_region cbr ON cbr.region_key = r.region_key
LEFT JOIN revenue_by_region rbr ON rbr.region_key = r.region_key
LEFT JOIN projects_by_region pbr ON pbr.region_key = r.region_key
LEFT JOIN support_by_region sbr ON sbr.region_key = r.region_key
WHERE r.region_key <> -1;

-- ============================================================
-- VW_SERVICE_PERFORMANCE -- grain: one row per service.
-- "Support activity" is intentionally NOT included: FACT_SUPPORT carries
-- no service_key or product linkage anywhere in STAGING/CORE, so there is
-- no real per-service ticket count to report -- see docs/analytics_layer.md.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_SERVICE_PERFORMANCE AS
WITH deals_by_service AS (
    SELECT service_key,
           COUNT(*) AS deal_count,
           SUM(IFF(is_won, 1, 0)) AS won_deals,
           SUM(IFF(is_won, net_deal_value, 0)) AS revenue
    FROM CORE.FACT_DEALS GROUP BY service_key
),
subs_by_service AS (
    SELECT service_key,
           COUNT(*) AS subscriptions,
           SUM(IFF(status = 'Active', arr, 0)) AS arr
    FROM CORE.FACT_SUBSCRIPTIONS GROUP BY service_key
),
projects_by_service AS (
    SELECT service_key, COUNT(*) AS projects
    FROM CORE.FACT_PROJECTS GROUP BY service_key
)
SELECT
    sv.service_name,
    sv.service_category,
    COALESCE(d.deal_count, 0)   AS deal_count,
    COALESCE(d.won_deals, 0)    AS won_deals,
    COALESCE(d.revenue, 0)      AS revenue,
    COALESCE(s.subscriptions, 0) AS subscriptions,
    COALESCE(s.arr, 0)          AS arr,
    COALESCE(p.projects, 0)     AS projects
FROM CORE.DIM_SERVICE sv
LEFT JOIN deals_by_service d ON d.service_key = sv.service_key
LEFT JOIN subs_by_service s ON s.service_key = sv.service_key
LEFT JOIN projects_by_service p ON p.service_key = sv.service_key
WHERE sv.service_key <> -1;

-- ============================================================
-- VW_AT_RISK_CUSTOMERS -- grain: one row per at-risk current customer
-- (churn_risk_category IN ('High','Critical')), ranked most-at-risk first.
-- risk_rank uses a fully deterministic ORDER BY (score, then customer_id
-- as a tiebreaker) so re-running the query always returns the same order.
-- ============================================================
CREATE OR REPLACE VIEW ANALYTICS.VW_AT_RISK_CUSTOMERS AS
WITH open_tickets AS (
    SELECT customer_key, COUNT(*) AS open_tickets
    FROM CORE.FACT_SUPPORT WHERE status IN ('Open','In Progress','Escalated')
    GROUP BY customer_key
),
project_risk AS (
    SELECT customer_key, AVG(project_risk_score) AS project_risk
    FROM CORE.FACT_PROJECTS GROUP BY customer_key
),
activity AS (
    SELECT a.customer_key, MAX(dt.full_date) AS last_activity
    FROM CORE.FACT_CUSTOMER_ACTIVITY a
    LEFT JOIN CORE.DIM_DATE dt ON dt.date_key = a.activity_date_key
    GROUP BY a.customer_key
)
SELECT
    ROW_NUMBER() OVER (ORDER BY c.churn_risk_score DESC, c.customer_id ASC) AS risk_rank,
    c.customer_id,
    c.company_name,
    (100 - c.churn_risk_score)          AS customer_health_score,
    c.churn_risk_category,
    c.annual_contract_value              AS revenue_exposure,
    COALESCE(ot.open_tickets, 0)         AS open_tickets,
    c.avg_payment_delay_days             AS payment_delays,
    pr.project_risk,
    act.last_activity
FROM CORE.DIM_CUSTOMER c
LEFT JOIN open_tickets ot ON ot.customer_key = c.customer_key
LEFT JOIN project_risk pr ON pr.customer_key = c.customer_key
LEFT JOIN activity act ON act.customer_key = c.customer_key
WHERE c.is_current = TRUE AND c.customer_key <> -1
  AND c.churn_risk_category IN ('High', 'Critical')
ORDER BY risk_rank;
