from backend.db.queries import support_metrics_query
from backend.db.snowflake import execute_query
from backend.models.support import SupportMetricsResponse


def get_support_metrics(priority, status, customer_id) -> SupportMetricsResponse:
    sql, params = support_metrics_query(priority, status, customer_id)
    rows = execute_query(sql, params=params, operation="support_metrics")
    row = rows[0] if rows else {}
    return SupportMetricsResponse(
        total_tickets=row.get("total_tickets") or 0,
        open_tickets=row.get("open_tickets") or 0,
        high_priority_tickets=row.get("high_priority_tickets") or 0,
        sla_breaches=row.get("sla_breaches") or 0,
        avg_resolution_time_hours=row.get("avg_resolution_time_hours"),
        avg_satisfaction_rating=row.get("avg_satisfaction_rating"),
    )
