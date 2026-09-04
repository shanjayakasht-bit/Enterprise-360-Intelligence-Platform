-- NEXORA Phase 2B: RAW -> STAGING transformations.
--
-- Strategy: FULL REFRESH, per table -- TRUNCATE STAGING.STG_* then
-- INSERT INTO ... SELECT ... FROM RAW.*. Idempotent: re-running produces
-- the same STAGING contents from whatever is currently in RAW. RAW is only
-- ever read here, never written -- it stays immutable source history.
--
-- Per table the pattern is:
--   1. base       -- clean/typecast every column straight from RAW, using
--                     TRIM/UPPER for IDs, TRIM+INITCAP for categorical
--                     fields (with acronym fix-ups where the source data
--                     intentionally uses one, e.g. "ACH"), TRY_TO_DATE /
--                     TRY_TO_DECIMAL / TRY_TO_BOOLEAN defensively so a bad
--                     value produces NULL instead of aborting the load.
--   2. deduped    -- ROW_NUMBER() PARTITION BY the cleaned primary key,
--                     newest _loaded_at first; only rn = 1 is kept, so a
--                     primary-key duplicate can never reach STAGING.
--   3. flagged    -- evaluates the data-quality rules (see
--                     docs/staging_data_quality.md) into two arrays,
--                     invalid_issues and warning_issues.
--   Final SELECT  -- INVALID if any invalid_issues fired, else WARNING if
--                     any warning_issues fired, else VALID. No row is ever
--                     dropped for failing a rule -- it is inserted with the
--                     status/issue text so downstream layers can filter or
--                     act on it explicitly.
--
-- Run after 04_staging_tables.sql:
--
--     snowsql -f snowflake/sql/05_staging_transformations.sql

USE DATABASE NEXORA_DB;
USE WAREHOUSE NEXORA_WH;

-- ============================================================
-- STG_CUSTOMERS
-- ============================================================
TRUNCATE TABLE STAGING.STG_CUSTOMERS;

INSERT INTO STAGING.STG_CUSTOMERS
WITH base AS (
    SELECT
        UPPER(TRIM(customer_id))                                    AS customer_id,
        TRIM(company_name)                                          AS company_name,
        TRIM(INITCAP(TRIM(industry)))                                AS industry,
        TRIM(INITCAP(TRIM(segment)))                                 AS segment,
        TRIM(INITCAP(TRIM(region)))                                  AS region,
        TRIM(INITCAP(TRIM(country)))                                 AS country,
        NULLIF(UPPER(TRIM(account_manager_id)), '')                  AS account_manager_id,
        TRIM(INITCAP(TRIM(subscription_plan)))                       AS subscription_plan,
        TRY_TO_DATE(TO_VARCHAR(signup_date))                         AS signup_date,
        TRY_TO_DATE(TO_VARCHAR(contract_start_date))                 AS contract_start_date,
        TRY_TO_DATE(TO_VARCHAR(renewal_date))                        AS renewal_date,
        TRY_TO_DECIMAL(TO_VARCHAR(annual_contract_value), 15, 2)     AS annual_contract_value,
        TRY_TO_DECIMAL(TO_VARCHAR(product_usage_score), 6, 2)        AS product_usage_score,
        TRY_TO_DECIMAL(TO_VARCHAR(engagement_score), 6, 2)           AS engagement_score,
        TRY_TO_DECIMAL(TO_VARCHAR(satisfaction_score), 6, 2)         AS satisfaction_score,
        TRY_TO_NUMBER(TO_VARCHAR(support_ticket_count_recent), 10, 0) AS support_ticket_count_recent,
        TRY_TO_DECIMAL(TO_VARCHAR(avg_payment_delay_days), 8, 2)     AS avg_payment_delay_days,
        TRY_TO_NUMBER(TO_VARCHAR(days_to_renewal), 10, 0)            AS days_to_renewal,
        TRY_TO_DECIMAL(TO_VARCHAR(churn_risk_score), 6, 2)           AS churn_risk_score,
        TRIM(INITCAP(TRIM(churn_risk_category)))                     AS churn_risk_category,
        _loaded_at                                                   AS _source_loaded_at
    FROM RAW.CUSTOMERS
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN company_name IS NULL THEN 'missing company_name' END,
            CASE WHEN segment IS NULL THEN 'missing segment' END,
            CASE WHEN region IS NULL THEN 'missing region' END,
            CASE WHEN signup_date IS NULL THEN 'missing/unparseable signup_date' END,
            CASE WHEN renewal_date IS NULL THEN 'missing/unparseable renewal_date' END,
            CASE WHEN product_usage_score IS NOT NULL AND (product_usage_score < 0 OR product_usage_score > 100) THEN 'product_usage_score out of [0,100]' END,
            CASE WHEN engagement_score IS NOT NULL AND (engagement_score < 0 OR engagement_score > 100) THEN 'engagement_score out of [0,100]' END,
            CASE WHEN satisfaction_score IS NOT NULL AND (satisfaction_score < 0 OR satisfaction_score > 100) THEN 'satisfaction_score out of [0,100]' END,
            CASE WHEN churn_risk_score IS NOT NULL AND (churn_risk_score < 0 OR churn_risk_score > 100) THEN 'churn_risk_score out of [0,100]' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN account_manager_id IS NULL THEN 'no account_manager_id' END,
            CASE WHEN churn_risk_category IS NOT NULL AND churn_risk_category NOT IN ('Low','Medium','High','Critical') THEN 'unexpected churn_risk_category value' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    customer_id, company_name, industry, segment, region, country, account_manager_id, subscription_plan,
    signup_date, contract_start_date, renewal_date, annual_contract_value, product_usage_score, engagement_score,
    satisfaction_score, support_ticket_count_recent, avg_payment_delay_days, days_to_renewal, churn_risk_score,
    churn_risk_category, _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_EMPLOYEES
-- ============================================================
TRUNCATE TABLE STAGING.STG_EMPLOYEES;

INSERT INTO STAGING.STG_EMPLOYEES
WITH base AS (
    SELECT
        UPPER(TRIM(employee_id))                              AS employee_id,
        TRIM(first_name)                                      AS first_name,
        TRIM(last_name)                                       AS last_name,
        TRIM(full_name)                                       AS full_name,
        LOWER(TRIM(email))                                    AS email,
        TRIM(INITCAP(TRIM(department)))                        AS department,
        REPLACE(INITCAP(TRIM(job_title)), 'Hr ', 'HR ')        AS job_title,
        TRIM(INITCAP(TRIM(region)))                            AS region,
        TRY_TO_DATE(TO_VARCHAR(hire_date))                    AS hire_date,
        NULLIF(UPPER(TRIM(manager_id)), '')                    AS manager_id,
        TRY_TO_DECIMAL(TO_VARCHAR(performance_score), 6, 2)   AS performance_score,
        TRY_TO_BOOLEAN(TO_VARCHAR(is_active))                 AS is_active,
        _loaded_at                                             AS _source_loaded_at
    FROM RAW.EMPLOYEES
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN employee_id IS NULL THEN 'missing employee_id' END,
            CASE WHEN full_name IS NULL THEN 'missing full_name' END,
            CASE WHEN department IS NULL THEN 'missing department' END,
            CASE WHEN hire_date IS NULL THEN 'missing/unparseable hire_date' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN performance_score IS NOT NULL AND (performance_score < 0 OR performance_score > 100) THEN 'performance_score out of [0,100]' END,
            CASE WHEN manager_id IS NULL AND department <> 'Executive' THEN 'no manager_id for non-Executive employee' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    employee_id, first_name, last_name, full_name, email, department, job_title, region, hire_date,
    manager_id, performance_score, is_active, _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_LEADS
-- ============================================================
TRUNCATE TABLE STAGING.STG_LEADS;

INSERT INTO STAGING.STG_LEADS
WITH base AS (
    SELECT
        UPPER(TRIM(lead_id))                                  AS lead_id,
        UPPER(TRIM(customer_id))                              AS customer_id,
        TRIM(INITCAP(TRIM(lead_source)))                       AS lead_source,
        TRY_TO_DATE(TO_VARCHAR(created_date))                 AS created_date,
        NULLIF(UPPER(TRIM(assigned_salesperson_id)), '')      AS assigned_salesperson_id,
        TRIM(INITCAP(TRIM(status)))                            AS status,
        TRY_TO_DECIMAL(TO_VARCHAR(lead_score), 6, 2)          AS lead_score,
        TRY_TO_BOOLEAN(TO_VARCHAR(converted_to_deal))         AS converted_to_deal,
        TRY_TO_DATE(TO_VARCHAR(converted_date))               AS converted_date,
        _loaded_at                                             AS _source_loaded_at
    FROM RAW.LEADS
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY lead_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN lead_id IS NULL THEN 'missing lead_id' END,
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN created_date IS NULL THEN 'missing/unparseable created_date' END,
            CASE WHEN status IS NULL THEN 'missing status' END,
            CASE WHEN lead_score IS NOT NULL AND (lead_score < 0 OR lead_score > 100) THEN 'lead_score out of [0,100]' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN converted_to_deal = TRUE AND converted_date IS NULL THEN 'converted lead missing converted_date' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    lead_id, customer_id, lead_source, created_date, assigned_salesperson_id, status, lead_score,
    converted_to_deal, converted_date, _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_DEALS
-- ============================================================
TRUNCATE TABLE STAGING.STG_DEALS;

INSERT INTO STAGING.STG_DEALS
WITH base AS (
    SELECT
        UPPER(TRIM(deal_id))                                  AS deal_id,
        UPPER(TRIM(customer_id))                              AS customer_id,
        NULLIF(UPPER(TRIM(lead_id)), '')                       AS lead_id,
        NULLIF(UPPER(TRIM(sales_rep_id)), '')                  AS sales_rep_id,
        TRIM(product)                                          AS product,
        TRIM(INITCAP(TRIM(deal_stage)))                        AS deal_stage,
        TRY_TO_BOOLEAN(TO_VARCHAR(is_won))                    AS is_won,
        TRY_TO_DECIMAL(TO_VARCHAR(deal_value), 15, 2)         AS deal_value,
        TRY_TO_DECIMAL(TO_VARCHAR(discount_pct), 6, 4)        AS discount_pct,
        TRY_TO_DATE(TO_VARCHAR(created_date))                 AS created_date,
        TRY_TO_DATE(TO_VARCHAR(close_date))                   AS close_date,
        TRIM(INITCAP(TRIM(region)))                            AS region,
        TRIM(INITCAP(TRIM(segment)))                           AS segment,
        _loaded_at                                             AS _source_loaded_at
    FROM RAW.DEALS
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN deal_id IS NULL THEN 'missing deal_id' END,
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN deal_stage IS NULL THEN 'missing deal_stage' END,
            CASE WHEN created_date IS NULL THEN 'missing/unparseable created_date' END,
            CASE WHEN discount_pct IS NOT NULL AND (discount_pct < 0 OR discount_pct > 1) THEN 'discount_pct out of [0,1]' END,
            CASE WHEN close_date IS NOT NULL AND created_date IS NOT NULL AND close_date < created_date THEN 'close_date before created_date' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN deal_value IS NOT NULL AND deal_value < 0 THEN 'negative deal_value' END,
            CASE WHEN is_won IS NOT NULL AND close_date IS NULL THEN 'decided deal missing close_date' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    deal_id, customer_id, lead_id, sales_rep_id, product, deal_stage, is_won, deal_value, discount_pct,
    created_date, close_date, region, segment, _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_SUBSCRIPTIONS
-- ============================================================
TRUNCATE TABLE STAGING.STG_SUBSCRIPTIONS;

INSERT INTO STAGING.STG_SUBSCRIPTIONS
WITH base AS (
    SELECT
        UPPER(TRIM(subscription_id))                          AS subscription_id,
        UPPER(TRIM(customer_id))                              AS customer_id,
        NULLIF(UPPER(TRIM(deal_id)), '')                       AS deal_id,
        TRIM(INITCAP(TRIM(plan)))                              AS plan,
        TRIM(INITCAP(TRIM(billing_cycle)))                     AS billing_cycle,
        TRY_TO_DATE(TO_VARCHAR(start_date))                   AS start_date,
        TRY_TO_DATE(TO_VARCHAR(end_date))                     AS end_date,
        TRY_TO_DECIMAL(TO_VARCHAR(mrr), 15, 2)                AS mrr,
        TRIM(INITCAP(TRIM(status)))                            AS status,
        TRY_TO_BOOLEAN(TO_VARCHAR(auto_renew))                AS auto_renew,
        _loaded_at                                             AS _source_loaded_at
    FROM RAW.SUBSCRIPTIONS
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY subscription_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN subscription_id IS NULL THEN 'missing subscription_id' END,
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN plan IS NULL THEN 'missing plan' END,
            CASE WHEN start_date IS NULL THEN 'missing/unparseable start_date' END,
            CASE WHEN end_date IS NOT NULL AND start_date IS NOT NULL AND end_date < start_date THEN 'end_date before start_date' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN mrr IS NOT NULL AND mrr < 0 THEN 'negative mrr' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    subscription_id, customer_id, deal_id, plan, billing_cycle, start_date, end_date, mrr, status,
    auto_renew, _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_PROJECTS
-- ============================================================
TRUNCATE TABLE STAGING.STG_PROJECTS;

INSERT INTO STAGING.STG_PROJECTS
WITH base AS (
    SELECT
        UPPER(TRIM(project_id))                               AS project_id,
        UPPER(TRIM(customer_id))                              AS customer_id,
        NULLIF(UPPER(TRIM(deal_id)), '')                       AS deal_id,
        NULLIF(UPPER(TRIM(project_manager_id)), '')            AS project_manager_id,
        TRIM(INITCAP(TRIM(project_type)))                      AS project_type,
        TRY_TO_DATE(TO_VARCHAR(start_date))                   AS start_date,
        TRY_TO_DATE(TO_VARCHAR(planned_end_date))             AS planned_end_date,
        TRY_TO_DATE(TO_VARCHAR(actual_end_date))              AS actual_end_date,
        TRIM(INITCAP(TRIM(status)))                            AS status,
        TRY_TO_DECIMAL(TO_VARCHAR(completion_pct), 6, 2)      AS completion_pct,
        TRY_TO_DECIMAL(TO_VARCHAR(budget), 15, 2)             AS budget,
        TRY_TO_DECIMAL(TO_VARCHAR(actual_cost), 15, 2)        AS actual_cost,
        TRY_TO_DECIMAL(TO_VARCHAR(budget_utilization_pct), 8, 2) AS budget_utilization_pct,
        TRY_TO_DECIMAL(TO_VARCHAR(cost_overrun_pct), 8, 2)    AS cost_overrun_pct,
        TRY_TO_DECIMAL(TO_VARCHAR(project_risk_score), 6, 2)  AS project_risk_score,
        TRIM(INITCAP(TRIM(project_risk_category)))             AS project_risk_category,
        _loaded_at                                             AS _source_loaded_at
    FROM RAW.PROJECTS
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN project_id IS NULL THEN 'missing project_id' END,
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN start_date IS NULL THEN 'missing/unparseable start_date' END,
            CASE WHEN status IS NULL THEN 'missing status' END,
            CASE WHEN completion_pct IS NOT NULL AND (completion_pct < 0 OR completion_pct > 100) THEN 'completion_pct out of [0,100]' END,
            CASE WHEN project_risk_score IS NOT NULL AND (project_risk_score < 0 OR project_risk_score > 100) THEN 'project_risk_score out of [0,100]' END,
            CASE WHEN planned_end_date IS NOT NULL AND start_date IS NOT NULL AND planned_end_date < start_date THEN 'planned_end_date before start_date' END,
            CASE WHEN actual_end_date IS NOT NULL AND start_date IS NOT NULL AND actual_end_date < start_date THEN 'actual_end_date before start_date' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN budget IS NOT NULL AND budget < 0 THEN 'negative budget' END,
            CASE WHEN actual_cost IS NOT NULL AND actual_cost < 0 THEN 'negative actual_cost' END,
            CASE WHEN status = 'Completed' AND actual_end_date IS NULL THEN 'Completed project missing actual_end_date' END,
            CASE WHEN project_risk_category IS NOT NULL AND project_risk_category NOT IN ('Low','Medium','High','Critical') THEN 'unexpected project_risk_category value' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    project_id, customer_id, deal_id, project_manager_id, project_type, start_date, planned_end_date,
    actual_end_date, status, completion_pct, budget, actual_cost, budget_utilization_pct, cost_overrun_pct,
    project_risk_score, project_risk_category, _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_INVOICES
-- ============================================================
TRUNCATE TABLE STAGING.STG_INVOICES;

INSERT INTO STAGING.STG_INVOICES
WITH base AS (
    SELECT
        UPPER(TRIM(invoice_id))                               AS invoice_id,
        UPPER(TRIM(customer_id))                              AS customer_id,
        NULLIF(UPPER(TRIM(subscription_id)), '')               AS subscription_id,
        NULLIF(UPPER(TRIM(project_id)), '')                    AS project_id,
        TRY_TO_DATE(TO_VARCHAR(invoice_date))                 AS invoice_date,
        TRY_TO_DATE(TO_VARCHAR(due_date))                     AS due_date,
        TRY_TO_DECIMAL(TO_VARCHAR(amount), 15, 2)             AS amount,
        TRY_TO_DECIMAL(TO_VARCHAR(tax), 15, 2)                AS tax,
        TRY_TO_DECIMAL(TO_VARCHAR(total_amount), 15, 2)       AS total_amount,
        TRIM(INITCAP(TRIM(status)))                            AS status,
        _loaded_at                                             AS _source_loaded_at
    FROM RAW.INVOICES
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY invoice_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN invoice_id IS NULL THEN 'missing invoice_id' END,
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN invoice_date IS NULL THEN 'missing/unparseable invoice_date' END,
            CASE WHEN due_date IS NULL THEN 'missing/unparseable due_date' END,
            CASE WHEN total_amount IS NULL THEN 'missing total_amount' END,
            CASE WHEN amount IS NOT NULL AND amount < 0 THEN 'negative amount' END,
            CASE WHEN total_amount IS NOT NULL AND total_amount < 0 THEN 'negative total_amount' END,
            CASE WHEN due_date IS NOT NULL AND invoice_date IS NOT NULL AND due_date < invoice_date THEN 'due_date before invoice_date' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN subscription_id IS NULL AND project_id IS NULL THEN 'standalone invoice (no subscription or project link)' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    invoice_id, customer_id, subscription_id, project_id, invoice_date, due_date, amount, tax, total_amount,
    status, _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_PAYMENTS
-- (joins RAW.INVOICES, not STG_INVOICES, so this table's transformation
--  never depends on another staging table having already been run.)
-- ============================================================
TRUNCATE TABLE STAGING.STG_PAYMENTS;

INSERT INTO STAGING.STG_PAYMENTS
WITH base AS (
    SELECT
        UPPER(TRIM(p.payment_id))                             AS payment_id,
        UPPER(TRIM(p.invoice_id))                             AS invoice_id,
        UPPER(TRIM(p.customer_id))                            AS customer_id,
        TRY_TO_DATE(TO_VARCHAR(p.payment_date))               AS payment_date,
        TRY_TO_DECIMAL(TO_VARCHAR(p.amount_paid), 15, 2)      AS amount_paid,
        TRIM(INITCAP(TRIM(p.payment_method)))                  AS payment_method,
        TRIM(INITCAP(TRIM(p.payment_status)))                  AS payment_status,
        TRY_TO_NUMBER(TO_VARCHAR(p.days_late), 10, 0)         AS days_late,
        p._loaded_at                                           AS _source_loaded_at,
        i.invoice_date                                         AS _invoice_date
    FROM RAW.PAYMENTS p
    LEFT JOIN RAW.INVOICES i ON UPPER(TRIM(p.invoice_id)) = UPPER(TRIM(i.invoice_id))
),
base_fixed AS (
    -- "ACH" is an intentional acronym in the source payment_method values; INITCAP
    -- lowercases it to "Ach", so restore it after standardizing everything else.
    SELECT * REPLACE (REPLACE(payment_method, 'Ach', 'ACH') AS payment_method)
    FROM base
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY payment_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base_fixed
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN payment_id IS NULL THEN 'missing payment_id' END,
            CASE WHEN invoice_id IS NULL THEN 'missing invoice_id' END,
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN payment_date IS NULL THEN 'missing/unparseable payment_date' END,
            CASE WHEN amount_paid IS NULL THEN 'missing amount_paid' END,
            CASE WHEN amount_paid IS NOT NULL AND amount_paid < 0 THEN 'negative amount_paid' END,
            CASE WHEN payment_date IS NOT NULL AND _invoice_date IS NOT NULL AND payment_date < _invoice_date THEN 'payment_date before invoice_date' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN _invoice_date IS NULL THEN 'invoice_id not found in RAW.INVOICES' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    payment_id, invoice_id, customer_id, payment_date, amount_paid, payment_method, payment_status, days_late,
    _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_SUPPORT_TICKETS
-- ============================================================
TRUNCATE TABLE STAGING.STG_SUPPORT_TICKETS;

INSERT INTO STAGING.STG_SUPPORT_TICKETS
WITH base AS (
    SELECT
        UPPER(TRIM(ticket_id))                                AS ticket_id,
        UPPER(TRIM(customer_id))                              AS customer_id,
        NULLIF(UPPER(TRIM(agent_id)), '')                      AS agent_id,
        TRIM(INITCAP(TRIM(category)))                          AS category,
        TRIM(INITCAP(TRIM(priority)))                          AS priority,
        TRIM(INITCAP(TRIM(channel)))                           AS channel,
        TRIM(INITCAP(TRIM(status)))                            AS status,
        TRY_TO_DATE(TO_VARCHAR(created_date))                 AS created_date,
        TRY_TO_DATE(TO_VARCHAR(resolution_date))              AS resolution_date,
        TRY_TO_DECIMAL(TO_VARCHAR(resolution_time_hours), 10, 2) AS resolution_time_hours,
        TRY_TO_DECIMAL(TO_VARCHAR(satisfaction_rating), 4, 2) AS satisfaction_rating,
        _loaded_at                                             AS _source_loaded_at
    FROM RAW.SUPPORT_TICKETS
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY ticket_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN ticket_id IS NULL THEN 'missing ticket_id' END,
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN created_date IS NULL THEN 'missing/unparseable created_date' END,
            CASE WHEN status IS NULL THEN 'missing status' END,
            CASE WHEN satisfaction_rating IS NOT NULL AND (satisfaction_rating < 1 OR satisfaction_rating > 5) THEN 'satisfaction_rating out of [1,5]' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN status IN ('Closed','Resolved') AND resolution_date IS NULL THEN 'closed/resolved ticket missing resolution_date' END,
            CASE WHEN resolution_date IS NOT NULL AND status NOT IN ('Closed','Resolved') THEN 'resolution_date set but status not closed/resolved' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    ticket_id, customer_id, agent_id, category, priority, channel, status, created_date, resolution_date,
    resolution_time_hours, satisfaction_rating, _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;


-- ============================================================
-- STG_CUSTOMER_ACTIVITY
-- ============================================================
TRUNCATE TABLE STAGING.STG_CUSTOMER_ACTIVITY;

INSERT INTO STAGING.STG_CUSTOMER_ACTIVITY
WITH base AS (
    SELECT
        UPPER(TRIM(activity_id))                              AS activity_id,
        UPPER(TRIM(customer_id))                              AS customer_id,
        TRY_TO_DATE(TO_VARCHAR(activity_date))                AS activity_date,
        REPLACE(INITCAP(TRIM(activity_type)), 'Api', 'API')    AS activity_type,
        TRY_TO_DECIMAL(TO_VARCHAR(duration_minutes), 10, 2)   AS duration_minutes,
        TRY_TO_DECIMAL(TO_VARCHAR(engagement_points), 10, 2)  AS engagement_points,
        _loaded_at                                             AS _source_loaded_at
    FROM RAW.CUSTOMER_ACTIVITY
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY activity_id ORDER BY _source_loaded_at DESC NULLS LAST) AS rn
    FROM base
),
flagged AS (
    SELECT *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN activity_id IS NULL THEN 'missing activity_id' END,
            CASE WHEN customer_id IS NULL THEN 'missing customer_id' END,
            CASE WHEN activity_date IS NULL THEN 'missing/unparseable activity_date' END
        ) AS invalid_issues,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN duration_minutes IS NOT NULL AND duration_minutes < 0 THEN 'negative duration_minutes' END,
            CASE WHEN engagement_points IS NOT NULL AND engagement_points < 0 THEN 'negative engagement_points' END
        ) AS warning_issues
    FROM deduped
    WHERE rn = 1
)
SELECT
    activity_id, customer_id, activity_date, activity_type, duration_minutes, engagement_points,
    _source_loaded_at, CURRENT_TIMESTAMP() AS _staged_at,
    CASE WHEN ARRAY_SIZE(invalid_issues) > 0 THEN 'INVALID' WHEN ARRAY_SIZE(warning_issues) > 0 THEN 'WARNING' ELSE 'VALID' END AS _data_quality_status,
    NULLIF(ARRAY_TO_STRING(ARRAY_CAT(invalid_issues, warning_issues), '; '), '') AS _data_quality_issue
FROM flagged;
