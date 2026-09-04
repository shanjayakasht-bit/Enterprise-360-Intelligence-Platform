-- NEXORA Phase 2C: CORE load logic.
--
-- Source: NEXORA_DB.STAGING, restricted to _data_quality_status IN
-- ('VALID','WARNING') everywhere below -- INVALID rows never reach CORE.
-- RAW and STAGING are only ever read here.
--
-- Load order (dimensions before facts; DIM_EMPLOYEE/DIM_CUSTOMER before the
-- other dimensions that reference them via surrogate key):
--   1. DIM_DATE, DIM_REGION, DIM_DEPARTMENT, DIM_SERVICE (Type 1, idempotent
--      insert-new-values-only -- never truncated, since there is nothing to
--      re-derive: the same distinct value always gets the same surrogate
--      key once assigned).
--   2. DIM_EMPLOYEE, then DIM_CUSTOMER (SCD Type 2 -- see the two-step
--      UPDATE-then-INSERT pattern at each, and docs/dimensional_model.md).
--      Never truncated: that would destroy history.
--   3. The eight FACT_* tables (full refresh: TRUNCATE + INSERT, since
--      facts carry no history-tracking requirement here).
--
-- Every dimension lookup that can't resolve falls back to surrogate key -1
-- (the Unknown member) via COALESCE, never to NULL and never by dropping
-- the fact row.
--
-- Idempotent: rerunning with unchanged STAGING data changes nothing (Type 1
-- dims insert 0 new rows, SCD2 dims expire/insert 0 rows since every hash
-- still matches, facts are fully rebuilt from the same source rows).
--
-- Run after snowflake/sql/07_core_facts.sql:
--
--     snowsql -f snowflake/sql/08_core_load.sql

USE DATABASE NEXORA_DB;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- DIM_DATE
-- ============================================================
-- @section: DIM_DATE
INSERT INTO CORE.DIM_DATE (date_key, full_date, day_of_month, day_name, day_of_week,
                            week_of_year, month_number, month_name, quarter, year, is_weekend)
WITH spine AS (
    SELECT DATEADD(day, SEQ4(), '2018-01-01'::DATE) AS full_date
    FROM TABLE(GENERATOR(ROWCOUNT => 4383))  -- 2018-01-01 .. 2029-12-31 inclusive
)
SELECT
    TO_NUMBER(TO_CHAR(full_date, 'YYYYMMDD')) AS date_key,
    full_date,
    DAY(full_date)          AS day_of_month,
    DAYNAME(full_date)      AS day_name,
    DAYOFWEEK(full_date)    AS day_of_week,
    WEEKOFYEAR(full_date)   AS week_of_year,
    MONTH(full_date)        AS month_number,
    MONTHNAME(full_date)    AS month_name,
    QUARTER(full_date)      AS quarter,
    YEAR(full_date)         AS year,
    IFF(DAYOFWEEK(full_date) IN (0, 6), TRUE, FALSE) AS is_weekend
FROM spine s
WHERE full_date <= '2029-12-31'::DATE
  AND NOT EXISTS (SELECT 1 FROM CORE.DIM_DATE d WHERE d.date_key = TO_NUMBER(TO_CHAR(s.full_date, 'YYYYMMDD')));

INSERT INTO CORE.DIM_DATE (date_key, full_date, day_of_month, day_name, day_of_week,
                            week_of_year, month_number, month_name, quarter, year, is_weekend)
SELECT -1, NULL, NULL, 'Unknown', NULL, NULL, NULL, 'Unknown', NULL, NULL, NULL
WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_DATE WHERE date_key = -1);

-- ============================================================
-- DIM_REGION (Type 1)
-- ============================================================
-- @section: DIM_REGION
INSERT INTO CORE.DIM_REGION (region_key, region_name)
SELECT CORE.SEQ_REGION_KEY.NEXTVAL, src.region_name
FROM (
    SELECT DISTINCT region AS region_name FROM STAGING.STG_CUSTOMERS WHERE _data_quality_status IN ('VALID','WARNING') AND region IS NOT NULL
    UNION
    SELECT DISTINCT region FROM STAGING.STG_EMPLOYEES WHERE _data_quality_status IN ('VALID','WARNING') AND region IS NOT NULL
    UNION
    SELECT DISTINCT region FROM STAGING.STG_DEALS WHERE _data_quality_status IN ('VALID','WARNING') AND region IS NOT NULL
) src
WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_REGION d WHERE d.region_name = src.region_name);

INSERT INTO CORE.DIM_REGION (region_key, region_name)
SELECT -1, 'Unknown'
WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_REGION WHERE region_key = -1);

-- ============================================================
-- DIM_DEPARTMENT (Type 1)
-- ============================================================
-- @section: DIM_DEPARTMENT
INSERT INTO CORE.DIM_DEPARTMENT (department_key, department_name)
SELECT CORE.SEQ_DEPARTMENT_KEY.NEXTVAL, src.department_name
FROM (
    SELECT DISTINCT department AS department_name FROM STAGING.STG_EMPLOYEES
    WHERE _data_quality_status IN ('VALID','WARNING') AND department IS NOT NULL
) src
WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_DEPARTMENT d WHERE d.department_name = src.department_name);

INSERT INTO CORE.DIM_DEPARTMENT (department_key, department_name)
SELECT -1, 'Unknown'
WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_DEPARTMENT WHERE department_key = -1);

-- ============================================================
-- DIM_SERVICE (Type 1) -- conformed from product / plan / project_type
-- ============================================================
-- @section: DIM_SERVICE
INSERT INTO CORE.DIM_SERVICE (service_key, service_name, service_category)
SELECT CORE.SEQ_SERVICE_KEY.NEXTVAL, src.service_name, src.service_category
FROM (
    SELECT DISTINCT product AS service_name, 'Product' AS service_category
    FROM STAGING.STG_DEALS WHERE _data_quality_status IN ('VALID','WARNING') AND product IS NOT NULL
    UNION
    SELECT DISTINCT plan, 'Subscription Plan'
    FROM STAGING.STG_SUBSCRIPTIONS WHERE _data_quality_status IN ('VALID','WARNING') AND plan IS NOT NULL
    UNION
    SELECT DISTINCT project_type, 'Project Type'
    FROM STAGING.STG_PROJECTS WHERE _data_quality_status IN ('VALID','WARNING') AND project_type IS NOT NULL
) src
WHERE NOT EXISTS (
    SELECT 1 FROM CORE.DIM_SERVICE d WHERE d.service_name = src.service_name AND d.service_category = src.service_category
);

INSERT INTO CORE.DIM_SERVICE (service_key, service_name, service_category)
SELECT -1, 'Unknown', 'Unknown'
WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_SERVICE WHERE service_key = -1);

-- ============================================================
-- DIM_EMPLOYEE (SCD Type 2)
-- Step 1: expire the current row for any employee_id whose tracked
--         attributes changed since the last load.
-- Step 2: insert a fresh current row for every employee_id that is either
--         brand new or was just expired in Step 1.
-- On a rerun with unchanged STAGING data, both steps affect zero rows.
-- ============================================================
-- @section: DIM_EMPLOYEE
UPDATE CORE.DIM_EMPLOYEE tgt
SET effective_to = DATEADD(day, -1, CURRENT_DATE()),
    is_current = FALSE
FROM (
    SELECT
        e.employee_id,
        HASH(CONCAT_WS('|',
            COALESCE(e.first_name, '~'), COALESCE(e.last_name, '~'), COALESCE(e.full_name, '~'),
            COALESCE(e.email, '~'), COALESCE(TO_VARCHAR(COALESCE(dep.department_key, -1)), '~'),
            COALESCE(e.job_title, '~'), COALESCE(TO_VARCHAR(COALESCE(reg.region_key, -1)), '~'),
            COALESCE(TO_VARCHAR(e.hire_date), '~'), COALESCE(e.manager_id, '~'),
            COALESCE(TO_VARCHAR(e.performance_score), '~'), COALESCE(TO_VARCHAR(e.is_active), '~')
        )) AS row_hash
    FROM STAGING.STG_EMPLOYEES e
    LEFT JOIN CORE.DIM_DEPARTMENT dep ON dep.department_name = e.department
    LEFT JOIN CORE.DIM_REGION reg ON reg.region_name = e.region
    WHERE e._data_quality_status IN ('VALID','WARNING')
) src
WHERE tgt.employee_id = src.employee_id
  AND tgt.is_current = TRUE
  AND tgt._row_hash <> src.row_hash;

INSERT INTO CORE.DIM_EMPLOYEE (
    employee_key, employee_id, first_name, last_name, full_name, email, department_key,
    job_title, region_key, hire_date, manager_id, performance_score, is_active,
    effective_from, effective_to, is_current, _row_hash, _source_loaded_at
)
WITH src AS (
    SELECT
        e.employee_id, e.first_name, e.last_name, e.full_name, e.email,
        COALESCE(dep.department_key, -1) AS department_key,
        e.job_title,
        COALESCE(reg.region_key, -1) AS region_key,
        e.hire_date, e.manager_id, e.performance_score, e.is_active,
        e._source_loaded_at,
        HASH(CONCAT_WS('|',
            COALESCE(e.first_name, '~'), COALESCE(e.last_name, '~'), COALESCE(e.full_name, '~'),
            COALESCE(e.email, '~'), COALESCE(TO_VARCHAR(COALESCE(dep.department_key, -1)), '~'),
            COALESCE(e.job_title, '~'), COALESCE(TO_VARCHAR(COALESCE(reg.region_key, -1)), '~'),
            COALESCE(TO_VARCHAR(e.hire_date), '~'), COALESCE(e.manager_id, '~'),
            COALESCE(TO_VARCHAR(e.performance_score), '~'), COALESCE(TO_VARCHAR(e.is_active), '~')
        )) AS row_hash
    FROM STAGING.STG_EMPLOYEES e
    LEFT JOIN CORE.DIM_DEPARTMENT dep ON dep.department_name = e.department
    LEFT JOIN CORE.DIM_REGION reg ON reg.region_name = e.region
    WHERE e._data_quality_status IN ('VALID','WARNING')
)
SELECT
    CORE.SEQ_EMPLOYEE_KEY.NEXTVAL, src.employee_id, src.first_name, src.last_name, src.full_name,
    src.email, src.department_key, src.job_title, src.region_key, src.hire_date, src.manager_id,
    src.performance_score, src.is_active,
    CURRENT_DATE() AS effective_from, NULL AS effective_to, TRUE AS is_current,
    src.row_hash, src._source_loaded_at
FROM src
WHERE NOT EXISTS (
    SELECT 1 FROM CORE.DIM_EMPLOYEE cur WHERE cur.employee_id = src.employee_id AND cur.is_current = TRUE
);

INSERT INTO CORE.DIM_EMPLOYEE (employee_key, employee_id, effective_from, is_current)
SELECT -1, '-1', CURRENT_DATE(), TRUE
WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_EMPLOYEE WHERE employee_key = -1);

-- ============================================================
-- DIM_CUSTOMER (SCD Type 2)
-- Same two-step pattern as DIM_EMPLOYEE. account_manager_key resolves to
-- the account manager's CURRENT DIM_EMPLOYEE row at load time.
-- ============================================================
-- @section: DIM_CUSTOMER
UPDATE CORE.DIM_CUSTOMER tgt
SET effective_to = DATEADD(day, -1, CURRENT_DATE()),
    is_current = FALSE
FROM (
    SELECT
        c.customer_id,
        HASH(CONCAT_WS('|',
            COALESCE(c.company_name, '~'), COALESCE(c.industry, '~'), COALESCE(c.segment, '~'),
            COALESCE(TO_VARCHAR(COALESCE(reg.region_key, -1)), '~'), COALESCE(c.country, '~'),
            COALESCE(TO_VARCHAR(COALESCE(mgr.employee_key, -1)), '~'), COALESCE(c.subscription_plan, '~'),
            COALESCE(TO_VARCHAR(c.contract_start_date), '~'), COALESCE(TO_VARCHAR(c.renewal_date), '~'),
            COALESCE(TO_VARCHAR(c.annual_contract_value), '~'), COALESCE(TO_VARCHAR(c.product_usage_score), '~'),
            COALESCE(TO_VARCHAR(c.engagement_score), '~'), COALESCE(TO_VARCHAR(c.satisfaction_score), '~'),
            COALESCE(TO_VARCHAR(c.support_ticket_count_recent), '~'), COALESCE(TO_VARCHAR(c.avg_payment_delay_days), '~'),
            COALESCE(TO_VARCHAR(c.days_to_renewal), '~'), COALESCE(TO_VARCHAR(c.churn_risk_score), '~'),
            COALESCE(c.churn_risk_category, '~')
        )) AS row_hash
    FROM STAGING.STG_CUSTOMERS c
    LEFT JOIN CORE.DIM_REGION reg ON reg.region_name = c.region
    LEFT JOIN CORE.DIM_EMPLOYEE mgr ON mgr.employee_id = c.account_manager_id AND mgr.is_current = TRUE
    WHERE c._data_quality_status IN ('VALID','WARNING')
) src
WHERE tgt.customer_id = src.customer_id
  AND tgt.is_current = TRUE
  AND tgt._row_hash <> src.row_hash;

INSERT INTO CORE.DIM_CUSTOMER (
    customer_key, customer_id, company_name, industry, segment, region_key, country,
    account_manager_key, subscription_plan, signup_date, contract_start_date, renewal_date,
    annual_contract_value, product_usage_score, engagement_score, satisfaction_score,
    support_ticket_count_recent, avg_payment_delay_days, days_to_renewal, churn_risk_score,
    churn_risk_category, effective_from, effective_to, is_current, _row_hash, _source_loaded_at
)
WITH src AS (
    SELECT
        c.customer_id, c.company_name, c.industry, c.segment,
        COALESCE(reg.region_key, -1) AS region_key, c.country,
        COALESCE(mgr.employee_key, -1) AS account_manager_key,
        c.subscription_plan, c.signup_date, c.contract_start_date, c.renewal_date,
        c.annual_contract_value, c.product_usage_score, c.engagement_score, c.satisfaction_score,
        c.support_ticket_count_recent, c.avg_payment_delay_days, c.days_to_renewal,
        c.churn_risk_score, c.churn_risk_category, c._source_loaded_at,
        HASH(CONCAT_WS('|',
            COALESCE(c.company_name, '~'), COALESCE(c.industry, '~'), COALESCE(c.segment, '~'),
            COALESCE(TO_VARCHAR(COALESCE(reg.region_key, -1)), '~'), COALESCE(c.country, '~'),
            COALESCE(TO_VARCHAR(COALESCE(mgr.employee_key, -1)), '~'), COALESCE(c.subscription_plan, '~'),
            COALESCE(TO_VARCHAR(c.contract_start_date), '~'), COALESCE(TO_VARCHAR(c.renewal_date), '~'),
            COALESCE(TO_VARCHAR(c.annual_contract_value), '~'), COALESCE(TO_VARCHAR(c.product_usage_score), '~'),
            COALESCE(TO_VARCHAR(c.engagement_score), '~'), COALESCE(TO_VARCHAR(c.satisfaction_score), '~'),
            COALESCE(TO_VARCHAR(c.support_ticket_count_recent), '~'), COALESCE(TO_VARCHAR(c.avg_payment_delay_days), '~'),
            COALESCE(TO_VARCHAR(c.days_to_renewal), '~'), COALESCE(TO_VARCHAR(c.churn_risk_score), '~'),
            COALESCE(c.churn_risk_category, '~')
        )) AS row_hash
    FROM STAGING.STG_CUSTOMERS c
    LEFT JOIN CORE.DIM_REGION reg ON reg.region_name = c.region
    LEFT JOIN CORE.DIM_EMPLOYEE mgr ON mgr.employee_id = c.account_manager_id AND mgr.is_current = TRUE
    WHERE c._data_quality_status IN ('VALID','WARNING')
)
SELECT
    CORE.SEQ_CUSTOMER_KEY.NEXTVAL, src.customer_id, src.company_name, src.industry, src.segment,
    src.region_key, src.country, src.account_manager_key, src.subscription_plan, src.signup_date,
    src.contract_start_date, src.renewal_date, src.annual_contract_value, src.product_usage_score,
    src.engagement_score, src.satisfaction_score, src.support_ticket_count_recent,
    src.avg_payment_delay_days, src.days_to_renewal, src.churn_risk_score, src.churn_risk_category,
    CURRENT_DATE() AS effective_from, NULL AS effective_to, TRUE AS is_current,
    src.row_hash, src._source_loaded_at
FROM src
WHERE NOT EXISTS (
    SELECT 1 FROM CORE.DIM_CUSTOMER cur WHERE cur.customer_id = src.customer_id AND cur.is_current = TRUE
);

INSERT INTO CORE.DIM_CUSTOMER (customer_key, customer_id, effective_from, is_current)
SELECT -1, '-1', CURRENT_DATE(), TRUE
WHERE NOT EXISTS (SELECT 1 FROM CORE.DIM_CUSTOMER WHERE customer_key = -1);

-- ============================================================
-- FACT_LEADS (full refresh)
-- ============================================================
-- @section: FACT_LEADS
TRUNCATE TABLE CORE.FACT_LEADS;

INSERT INTO CORE.FACT_LEADS
SELECT
    l.lead_id,
    COALESCE(cust.customer_key, -1),
    COALESCE(emp.employee_key, -1),
    COALESCE(TO_NUMBER(TO_CHAR(l.created_date, 'YYYYMMDD')), -1),
    COALESCE(TO_NUMBER(TO_CHAR(l.converted_date, 'YYYYMMDD')), -1),
    l.lead_source, l.status, l.lead_score, l.converted_to_deal,
    l._source_loaded_at, CURRENT_TIMESTAMP()
FROM STAGING.STG_LEADS l
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_id = l.customer_id AND cust.is_current = TRUE
LEFT JOIN CORE.DIM_EMPLOYEE emp ON emp.employee_id = l.assigned_salesperson_id AND emp.is_current = TRUE
WHERE l._data_quality_status IN ('VALID','WARNING');

-- ============================================================
-- FACT_DEALS (full refresh)
-- ============================================================
-- @section: FACT_DEALS
TRUNCATE TABLE CORE.FACT_DEALS;

INSERT INTO CORE.FACT_DEALS
SELECT
    d.deal_id,
    COALESCE(cust.customer_key, -1),
    COALESCE(emp.employee_key, -1),
    COALESCE(svc.service_key, -1),
    COALESCE(reg.region_key, -1),
    d.lead_id, d.deal_stage, d.segment,
    COALESCE(TO_NUMBER(TO_CHAR(d.created_date, 'YYYYMMDD')), -1),
    COALESCE(TO_NUMBER(TO_CHAR(d.close_date, 'YYYYMMDD')), -1),
    d.deal_value, d.discount_pct,
    ROUND(d.deal_value * (1 - d.discount_pct), 2) AS net_deal_value,
    d.is_won, d._source_loaded_at, CURRENT_TIMESTAMP()
FROM STAGING.STG_DEALS d
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_id = d.customer_id AND cust.is_current = TRUE
LEFT JOIN CORE.DIM_EMPLOYEE emp ON emp.employee_id = d.sales_rep_id AND emp.is_current = TRUE
LEFT JOIN CORE.DIM_SERVICE svc ON svc.service_name = d.product AND svc.service_category = 'Product'
LEFT JOIN CORE.DIM_REGION reg ON reg.region_name = d.region
WHERE d._data_quality_status IN ('VALID','WARNING');

-- ============================================================
-- FACT_SUBSCRIPTIONS (full refresh)
-- ============================================================
-- @section: FACT_SUBSCRIPTIONS
TRUNCATE TABLE CORE.FACT_SUBSCRIPTIONS;

INSERT INTO CORE.FACT_SUBSCRIPTIONS
SELECT
    s.subscription_id,
    COALESCE(cust.customer_key, -1),
    COALESCE(svc.service_key, -1),
    s.deal_id, s.billing_cycle, s.status,
    COALESCE(TO_NUMBER(TO_CHAR(s.start_date, 'YYYYMMDD')), -1),
    COALESCE(TO_NUMBER(TO_CHAR(s.end_date, 'YYYYMMDD')), -1),
    s.mrr, ROUND(s.mrr * 12, 2) AS arr, s.auto_renew,
    s._source_loaded_at, CURRENT_TIMESTAMP()
FROM STAGING.STG_SUBSCRIPTIONS s
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_id = s.customer_id AND cust.is_current = TRUE
LEFT JOIN CORE.DIM_SERVICE svc ON svc.service_name = s.plan AND svc.service_category = 'Subscription Plan'
WHERE s._data_quality_status IN ('VALID','WARNING');

-- ============================================================
-- FACT_PROJECTS (full refresh)
-- ============================================================
-- @section: FACT_PROJECTS
TRUNCATE TABLE CORE.FACT_PROJECTS;

INSERT INTO CORE.FACT_PROJECTS
SELECT
    p.project_id,
    COALESCE(cust.customer_key, -1),
    COALESCE(emp.employee_key, -1),
    COALESCE(svc.service_key, -1),
    p.deal_id, p.status, p.project_risk_category,
    COALESCE(TO_NUMBER(TO_CHAR(p.start_date, 'YYYYMMDD')), -1),
    COALESCE(TO_NUMBER(TO_CHAR(p.planned_end_date, 'YYYYMMDD')), -1),
    COALESCE(TO_NUMBER(TO_CHAR(p.actual_end_date, 'YYYYMMDD')), -1),
    p.completion_pct, p.budget, p.actual_cost, p.budget_utilization_pct,
    p.cost_overrun_pct, p.project_risk_score,
    p._source_loaded_at, CURRENT_TIMESTAMP()
FROM STAGING.STG_PROJECTS p
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_id = p.customer_id AND cust.is_current = TRUE
LEFT JOIN CORE.DIM_EMPLOYEE emp ON emp.employee_id = p.project_manager_id AND emp.is_current = TRUE
LEFT JOIN CORE.DIM_SERVICE svc ON svc.service_name = p.project_type AND svc.service_category = 'Project Type'
WHERE p._data_quality_status IN ('VALID','WARNING');

-- ============================================================
-- FACT_INVOICES (full refresh)
-- ============================================================
-- @section: FACT_INVOICES
TRUNCATE TABLE CORE.FACT_INVOICES;

INSERT INTO CORE.FACT_INVOICES
SELECT
    i.invoice_id,
    COALESCE(cust.customer_key, -1),
    i.subscription_id, i.project_id, i.status,
    COALESCE(TO_NUMBER(TO_CHAR(i.invoice_date, 'YYYYMMDD')), -1),
    COALESCE(TO_NUMBER(TO_CHAR(i.due_date, 'YYYYMMDD')), -1),
    i.amount, i.tax, i.total_amount,
    i._source_loaded_at, CURRENT_TIMESTAMP()
FROM STAGING.STG_INVOICES i
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_id = i.customer_id AND cust.is_current = TRUE
WHERE i._data_quality_status IN ('VALID','WARNING');

-- ============================================================
-- FACT_PAYMENTS (full refresh)
-- ============================================================
-- @section: FACT_PAYMENTS
TRUNCATE TABLE CORE.FACT_PAYMENTS;

INSERT INTO CORE.FACT_PAYMENTS
SELECT
    p.payment_id, p.invoice_id,
    COALESCE(cust.customer_key, -1),
    COALESCE(TO_NUMBER(TO_CHAR(p.payment_date, 'YYYYMMDD')), -1),
    p.payment_method, p.payment_status, p.amount_paid, p.days_late,
    p._source_loaded_at, CURRENT_TIMESTAMP()
FROM STAGING.STG_PAYMENTS p
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_id = p.customer_id AND cust.is_current = TRUE
WHERE p._data_quality_status IN ('VALID','WARNING');

-- ============================================================
-- FACT_SUPPORT (full refresh)
-- ============================================================
-- @section: FACT_SUPPORT
TRUNCATE TABLE CORE.FACT_SUPPORT;

INSERT INTO CORE.FACT_SUPPORT
SELECT
    t.ticket_id,
    COALESCE(cust.customer_key, -1),
    COALESCE(emp.employee_key, -1),
    t.category, t.priority, t.channel, t.status,
    COALESCE(TO_NUMBER(TO_CHAR(t.created_date, 'YYYYMMDD')), -1),
    COALESCE(TO_NUMBER(TO_CHAR(t.resolution_date, 'YYYYMMDD')), -1),
    t.resolution_time_hours, t.satisfaction_rating,
    t._source_loaded_at, CURRENT_TIMESTAMP()
FROM STAGING.STG_SUPPORT_TICKETS t
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_id = t.customer_id AND cust.is_current = TRUE
LEFT JOIN CORE.DIM_EMPLOYEE emp ON emp.employee_id = t.agent_id AND emp.is_current = TRUE
WHERE t._data_quality_status IN ('VALID','WARNING');

-- ============================================================
-- FACT_CUSTOMER_ACTIVITY (full refresh)
-- ============================================================
-- @section: FACT_CUSTOMER_ACTIVITY
TRUNCATE TABLE CORE.FACT_CUSTOMER_ACTIVITY;

INSERT INTO CORE.FACT_CUSTOMER_ACTIVITY
SELECT
    a.activity_id,
    COALESCE(cust.customer_key, -1),
    COALESCE(TO_NUMBER(TO_CHAR(a.activity_date, 'YYYYMMDD')), -1),
    a.activity_type, a.duration_minutes, a.engagement_points,
    a._source_loaded_at, CURRENT_TIMESTAMP()
FROM STAGING.STG_CUSTOMER_ACTIVITY a
LEFT JOIN CORE.DIM_CUSTOMER cust ON cust.customer_id = a.customer_id AND cust.is_current = TRUE
WHERE a._data_quality_status IN ('VALID','WARNING');
