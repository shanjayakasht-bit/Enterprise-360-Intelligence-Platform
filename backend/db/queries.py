"""Centralized, reviewable SQL for every endpoint. Every dynamic FILTER
VALUE is passed through the Snowflake connector's own parameter binding
(`%s` placeholders + a params tuple) -- never string-interpolated into the
SQL text. The one place a caller-influenced token selects something other
than a plain value (the revenue-trends `period` grain) uses a fixed
allowlist dict, never a raw column/expression built from user input.

Every function here returns (sql, params) and does not execute anything --
execution stays in backend/db/snowflake.py, called from the service layer.
"""

from backend.core.exceptions import InvalidFilterError

# ============================================================
# Overview
# ============================================================

OVERVIEW_SQL = """
SELECT
    o.total_revenue, o.active_customers, o.active_subscriptions, o.active_projects,
    o.projects_at_risk, o.open_support_tickets, o.support_sla_percentage,
    o.average_customer_health, o.total_invoice_amount, o.total_payments_received,
    o.outstanding_amount, o.enterprise_health_score,
    s.critical_decisions, s.high_priority_decisions, s.customers_at_risk,
    s.revenue_at_risk, s.projects_at_risk AS decision_projects_at_risk,
    s.payment_value_at_risk, s.revenue_opportunity_value
FROM ANALYTICS.VW_EXECUTIVE_OVERVIEW o
CROSS JOIN ANALYTICS.DI_EXECUTIVE_SUMMARY s
"""

# ============================================================
# Customers
# ============================================================

CUSTOMER_FILTER_COLUMNS = {
    "region": "c360.region",
    "segment": "c360.segment",
    "risk_level": "ml.risk_level",
}


def _customer_filters(region=None, segment=None, risk_level=None, search=None):
    clauses, params = [], []
    if region is not None:
        clauses.append(f"{CUSTOMER_FILTER_COLUMNS['region']} = %s")
        params.append(region)
    if segment is not None:
        clauses.append(f"{CUSTOMER_FILTER_COLUMNS['segment']} = %s")
        params.append(segment)
    if risk_level is not None:
        if risk_level not in ("Low", "Medium", "High"):
            raise InvalidFilterError("risk_level must be one of: Low, Medium, High")
        clauses.append(f"{CUSTOMER_FILTER_COLUMNS['risk_level']} = %s")
        params.append(risk_level)
    if search is not None:
        clauses.append("(c360.company_name ILIKE %s OR c360.customer_id ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


CUSTOMER_LIST_BASE = """
FROM ANALYTICS.VW_CUSTOMER_360 c360
LEFT JOIN ANALYTICS.ML_CUSTOMER_RISK ml ON ml.customer_id = c360.customer_id
LEFT JOIN ANALYTICS.DM_CUSTOMER_SEGMENTS seg ON seg.customer_id = c360.customer_id
"""


def customer_list_query(region, segment, risk_level, search, limit, offset):
    where, params = _customer_filters(region, segment, risk_level, search)
    sql = f"""
        SELECT
            c360.customer_id, c360.company_name, c360.segment, c360.region, c360.industry,
            c360.total_revenue, c360.arr, c360.customer_health_score, c360.customer_status,
            ml.risk_probability, ml.risk_level,
            seg.segment_name AS cluster_segment_name
        {CUSTOMER_LIST_BASE}
        {where}
        ORDER BY c360.customer_id
        LIMIT %s OFFSET %s
    """
    return sql, [*params, limit, offset]


def customer_count_query(region, segment, risk_level, search):
    where, params = _customer_filters(region, segment, risk_level, search)
    sql = f"SELECT COUNT(*) AS total {CUSTOMER_LIST_BASE} {where}"
    return sql, params


CUSTOMER_DETAIL_SQL = """
SELECT
    c360.*,
    h.churn_risk_score, h.churn_risk_category, h.risk_classification AS health_risk_classification,
    h.renewal_date, h.days_to_renewal,
    ml.risk_probability, ml.predicted_class, ml.risk_level AS ml_risk_level, ml.model_version AS ml_model_version,
    seg.cluster_id, seg.segment_name AS cluster_segment_name, seg.distance_from_centroid
FROM ANALYTICS.VW_CUSTOMER_360 c360
LEFT JOIN ANALYTICS.VW_CUSTOMER_HEALTH h ON h.customer_id = c360.customer_id
LEFT JOIN ANALYTICS.ML_CUSTOMER_RISK ml ON ml.customer_id = c360.customer_id
LEFT JOIN ANALYTICS.DM_CUSTOMER_SEGMENTS seg ON seg.customer_id = c360.customer_id
WHERE c360.customer_id = %s
"""

CUSTOMER_DECISIONS_SQL = """
SELECT decision_id, decision_type, title, severity, priority_score, status, generated_at
FROM ANALYTICS.DI_DECISIONS
WHERE entity_type = 'CUSTOMER' AND entity_id = %s
ORDER BY priority_score DESC
"""

# ============================================================
# Revenue
# ============================================================

# Allowlisted aggregation grains -- never a raw column list built from
# caller input. "service" is intentionally NOT a grain here: VW_REVENUE_TRENDS
# has no service dimension (a deliberate Phase 2D decision -- see
# docs/analytics_layer.md), so a `service` filter is accepted for interface
# consistency but has no matching column to filter on; see docs/api_reference.md.
REVENUE_PERIOD_GRAINS = {
    "daily": "full_date, full_date AS period_label",
    "monthly": "DATE_TRUNC('month', full_date) AS full_date, month_name || ' ' || year AS period_label",
    "quarterly": "DATE_TRUNC('quarter', full_date) AS full_date, 'Q' || quarter || ' ' || year AS period_label",
    "yearly": "DATE_TRUNC('year', full_date) AS full_date, TO_VARCHAR(year) AS period_label",
}


def revenue_trends_query(period, region, segment):
    if period is None:
        period = "monthly"
    if period not in REVENUE_PERIOD_GRAINS:
        raise InvalidFilterError(f"period must be one of: {', '.join(REVENUE_PERIOD_GRAINS)}")

    clauses, params = [], []
    if region is not None:
        clauses.append("region_name = %s")
        params.append(region)
    if segment is not None:
        clauses.append("segment = %s")
        params.append(segment)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    grain_expr = REVENUE_PERIOD_GRAINS[period]
    sql = f"""
        SELECT
            {grain_expr},
            SUM(deal_revenue) AS deal_revenue,
            SUM(subscription_mrr_booked) AS subscription_mrr_booked,
            SUM(subscription_arr_booked) AS subscription_arr_booked,
            SUM(invoice_amount) AS invoice_amount,
            SUM(payments_received) AS payments_received
        FROM ANALYTICS.VW_REVENUE_TRENDS
        {where}
        GROUP BY 1, 2
        ORDER BY 1
    """
    return sql, params


REVENUE_FORECAST_SQL = """
SELECT forecast_date, predicted_revenue, lower_bound, upper_bound, model_version, generated_at
FROM ANALYTICS.ML_REVENUE_FORECAST
ORDER BY forecast_date
"""

REVENUE_HISTORICAL_CONTEXT_SQL = """
SELECT DATE_TRUNC('month', full_date) AS month, SUM(invoice_amount) AS invoice_amount
FROM ANALYTICS.VW_REVENUE_TRENDS
GROUP BY 1
ORDER BY 1 DESC
LIMIT 12
"""

# ============================================================
# Projects
# ============================================================

PROJECT_FILTER_COLUMNS = {"risk_level": "ml.risk_level", "department": "p.department_name", "customer_id": "p.customer_id"}


def _project_filters(risk_level, department, customer_id):
    clauses, params = [], []
    if risk_level is not None:
        if risk_level not in ("Low", "Medium", "High"):
            raise InvalidFilterError("risk_level must be one of: Low, Medium, High")
        clauses.append(f"{PROJECT_FILTER_COLUMNS['risk_level']} = %s")
        params.append(risk_level)
    if department is not None:
        clauses.append(f"{PROJECT_FILTER_COLUMNS['department']} = %s")
        params.append(department)
    if customer_id is not None:
        clauses.append(f"{PROJECT_FILTER_COLUMNS['customer_id']} = %s")
        params.append(customer_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


PROJECT_LIST_BASE = """
FROM ANALYTICS.VW_PROJECT_RISK p
LEFT JOIN ANALYTICS.ML_PROJECT_RISK ml ON ml.project_id = p.project_id
"""


def project_risk_list_query(risk_level, department, customer_id, limit, offset):
    where, params = _project_filters(risk_level, department, customer_id)
    sql = f"""
        SELECT
            p.project_id, p.customer_id, p.company_name, p.department_name,
            p.project_manager_name, p.status, p.budget, p.actual_cost,
            p.completion_pct, p.project_risk_category, p.days_to_deadline,
            ml.risk_probability, ml.risk_level
        {PROJECT_LIST_BASE}
        {where}
        ORDER BY p.project_risk_score DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    return sql, [*params, limit, offset]


def project_risk_count_query(risk_level, department, customer_id):
    where, params = _project_filters(risk_level, department, customer_id)
    sql = f"SELECT COUNT(*) AS total {PROJECT_LIST_BASE} {where}"
    return sql, params


PROJECT_DETAIL_SQL = """
SELECT p.*, ml.risk_probability, ml.predicted_risk_class, ml.risk_level AS ml_risk_level, ml.model_version AS ml_model_version
FROM ANALYTICS.VW_PROJECT_RISK p
LEFT JOIN ANALYTICS.ML_PROJECT_RISK ml ON ml.project_id = p.project_id
WHERE p.project_id = %s
"""

PROJECT_DECISIONS_SQL = """
SELECT decision_id, decision_type, title, severity, priority_score, status, generated_at
FROM ANALYTICS.DI_DECISIONS
WHERE entity_type = 'PROJECT' AND entity_id = %s
ORDER BY priority_score DESC
"""

# ============================================================
# Support
# ============================================================

SUPPORT_FILTER_COLUMNS = {"priority": "priority", "status": "status", "customer_id": "customer_id"}


def support_metrics_query(priority, status_, customer_id):
    clauses, params = [], []
    if priority is not None:
        clauses.append(f"{SUPPORT_FILTER_COLUMNS['priority']} = %s")
        params.append(priority)
    if status_ is not None:
        clauses.append(f"{SUPPORT_FILTER_COLUMNS['status']} = %s")
        params.append(status_)
    if customer_id is not None:
        clauses.append(f"{SUPPORT_FILTER_COLUMNS['customer_id']} = %s")
        params.append(customer_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT
            COUNT(*) AS total_tickets,
            COUNT_IF(status IN ('Open', 'In Progress', 'Escalated')) AS open_tickets,
            COUNT_IF(priority IN ('High', 'Critical')) AS high_priority_tickets,
            COUNT_IF(sla_breach) AS sla_breaches,
            AVG(resolution_time_hours) AS avg_resolution_time_hours,
            AVG(satisfaction_rating) AS avg_satisfaction_rating
        FROM ANALYTICS.VW_SUPPORT_HEALTH
        {where}
    """
    return sql, params

# ============================================================
# Predictions (thin paginated wrappers over the ML_* tables)
# ============================================================

PREDICTION_TABLES = {
    "customers": ("ANALYTICS.ML_CUSTOMER_RISK", "risk_probability"),
    "projects": ("ANALYTICS.ML_PROJECT_RISK", "risk_probability"),
    "payments": ("ANALYTICS.ML_PAYMENT_DELAY", "delay_probability"),
}


def prediction_list_query(kind, risk_level, limit, offset):
    table, order_col = PREDICTION_TABLES[kind]
    clauses, params = [], []
    if risk_level is not None:
        if risk_level not in ("Low", "Medium", "High"):
            raise InvalidFilterError("risk_level must be one of: Low, Medium, High")
        clauses.append("risk_level = %s")
        params.append(risk_level)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM {table} {where} ORDER BY {order_col} DESC NULLS LAST LIMIT %s OFFSET %s"
    return sql, [*params, limit, offset]


def prediction_count_query(kind, risk_level):
    table, _ = PREDICTION_TABLES[kind]
    clauses, params = [], []
    if risk_level is not None:
        clauses.append("risk_level = %s")
        params.append(risk_level)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return f"SELECT COUNT(*) AS total FROM {table} {where}", params


REVENUE_PREDICTION_SQL = "SELECT * FROM ANALYTICS.ML_REVENUE_FORECAST ORDER BY forecast_date"

# ============================================================
# Decisions
# ============================================================

DECISION_FILTER_COLUMNS = {"severity": "severity", "decision_type": "decision_type", "entity_type": "entity_type", "status": "status"}


def _decision_filters(severity, decision_type, entity_type, status_):
    clauses, params = [], []
    if severity is not None:
        if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            raise InvalidFilterError("severity must be one of: LOW, MEDIUM, HIGH, CRITICAL")
        clauses.append(f"{DECISION_FILTER_COLUMNS['severity']} = %s")
        params.append(severity)
    if decision_type is not None:
        clauses.append(f"{DECISION_FILTER_COLUMNS['decision_type']} = %s")
        params.append(decision_type)
    if entity_type is not None:
        clauses.append(f"{DECISION_FILTER_COLUMNS['entity_type']} = %s")
        params.append(entity_type)
    if status_ is not None:
        if status_ not in ("NEW", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "DISMISSED"):
            raise InvalidFilterError("status must be one of: NEW, ACKNOWLEDGED, IN_PROGRESS, RESOLVED, DISMISSED")
        clauses.append(f"{DECISION_FILTER_COLUMNS['status']} = %s")
        params.append(status_)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def decision_list_query(severity, decision_type, entity_type, status_, limit, offset):
    where, params = _decision_filters(severity, decision_type, entity_type, status_)
    sql = f"""
        SELECT *
        FROM ANALYTICS.DI_DECISIONS
        {where}
        ORDER BY priority_score DESC, generated_at DESC
        LIMIT %s OFFSET %s
    """
    return sql, [*params, limit, offset]


def decision_count_query(severity, decision_type, entity_type, status_):
    where, params = _decision_filters(severity, decision_type, entity_type, status_)
    return f"SELECT COUNT(*) AS total FROM ANALYTICS.DI_DECISIONS {where}", params


DECISION_DETAIL_SQL = "SELECT * FROM ANALYTICS.DI_DECISIONS WHERE decision_id = %s"

DECISION_SUMMARY_SQL = "SELECT * FROM ANALYTICS.DI_EXECUTIVE_SUMMARY"

# ============================================================
# Metadata
# ============================================================

METADATA_REGIONS_SQL = "SELECT region_name FROM CORE.DIM_REGION WHERE region_key <> -1 ORDER BY region_name"
METADATA_SERVICES_SQL = "SELECT service_name, service_category FROM CORE.DIM_SERVICE WHERE service_key <> -1 ORDER BY service_category, service_name"
METADATA_SEGMENTS_SQL = "SELECT DISTINCT segment FROM ANALYTICS.VW_CUSTOMER_360 WHERE segment IS NOT NULL ORDER BY segment"
METADATA_DEPARTMENTS_SQL = "SELECT department_name FROM CORE.DIM_DEPARTMENT WHERE department_key <> -1 ORDER BY department_name"
