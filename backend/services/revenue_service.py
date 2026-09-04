from backend.db.queries import (
    REVENUE_FORECAST_SQL, REVENUE_HISTORICAL_CONTEXT_SQL, revenue_trends_query,
)
from backend.db.snowflake import execute_query
from backend.models.revenue import (
    RevenueForecastPoint, RevenueForecastResponse, RevenueHistoricalPoint,
    RevenueTrendPoint, RevenueTrendsResponse,
)


def get_revenue_trends(period, region, segment) -> RevenueTrendsResponse:
    sql, params = revenue_trends_query(period, region, segment)
    rows = execute_query(sql, params=params, operation="revenue_trends")
    points = [
        RevenueTrendPoint(
            period_start=row["full_date"], period_label=row.get("period_label"),
            deal_revenue=row.get("deal_revenue"), subscription_mrr_booked=row.get("subscription_mrr_booked"),
            subscription_arr_booked=row.get("subscription_arr_booked"), invoice_amount=row.get("invoice_amount"),
            payments_received=row.get("payments_received"),
        )
        for row in rows
    ]
    return RevenueTrendsResponse(period=period or "monthly", points=points)


def get_revenue_forecast() -> RevenueForecastResponse:
    historical_rows = execute_query(REVENUE_HISTORICAL_CONTEXT_SQL, operation="revenue_historical")
    forecast_rows = execute_query(REVENUE_FORECAST_SQL, operation="revenue_forecast")
    return RevenueForecastResponse(
        historical_context=[RevenueHistoricalPoint(**row) for row in reversed(historical_rows)],
        forecast=[RevenueForecastPoint(**row) for row in forecast_rows],
    )
