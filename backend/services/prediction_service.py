"""Serves already-computed Phase 4 model predictions straight from their
ML_* tables -- this layer never trains, retrains, or scores a model."""

from backend.db.queries import (
    REVENUE_PREDICTION_SQL, prediction_count_query, prediction_list_query,
)
from backend.db.snowflake import execute_query
from backend.models.prediction import (
    CustomerRiskPredictionRow, PaymentDelayPredictionRow, ProjectRiskPredictionRow,
)
from backend.models.revenue import RevenueForecastPoint
from backend.utils.pagination import Pagination, build_page_info

_MODELS = {
    "customers": CustomerRiskPredictionRow,
    "projects": ProjectRiskPredictionRow,
    "payments": PaymentDelayPredictionRow,
}


def list_predictions(kind: str, pagination: Pagination, risk_level):
    sql, params = prediction_list_query(kind, risk_level, pagination.limit, pagination.offset)
    rows = execute_query(sql, params=params, operation=f"predictions_{kind}_list")

    count_sql, count_params = prediction_count_query(kind, risk_level)
    total = execute_query(count_sql, params=count_params, operation=f"predictions_{kind}_count")[0]["total"]

    model = _MODELS[kind]
    items = [model(**row) for row in rows]
    return items, build_page_info(pagination, total)


def list_revenue_predictions():
    rows = execute_query(REVENUE_PREDICTION_SQL, operation="predictions_revenue")
    return [RevenueForecastPoint(**row) for row in rows]
