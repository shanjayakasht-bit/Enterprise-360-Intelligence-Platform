from backend.core.exceptions import ResourceNotFoundError
from backend.db.queries import (
    DECISION_DETAIL_SQL, DECISION_SUMMARY_SQL, decision_count_query, decision_list_query,
)
from backend.db.snowflake import execute_query
from backend.models.decision import DecisionCard, DecisionSummaryResponse
from backend.utils.pagination import Pagination, build_page_info


def list_decisions(pagination: Pagination, severity, decision_type, entity_type, status):
    sql, params = decision_list_query(severity, decision_type, entity_type, status, pagination.limit, pagination.offset)
    rows = execute_query(sql, params=params, operation="decisions_list")

    count_sql, count_params = decision_count_query(severity, decision_type, entity_type, status)
    total = execute_query(count_sql, params=count_params, operation="decisions_count")[0]["total"]

    items = [DecisionCard.from_row(row) for row in rows]
    return items, build_page_info(pagination, total)


def get_decision_detail(decision_id: str) -> DecisionCard:
    rows = execute_query(DECISION_DETAIL_SQL, params=[decision_id], operation="decision_detail")
    if not rows:
        raise ResourceNotFoundError(f"Decision '{decision_id}' was not found.")
    return DecisionCard.from_row(rows[0])


def get_decision_summary() -> DecisionSummaryResponse:
    rows = execute_query(DECISION_SUMMARY_SQL, operation="decision_summary")
    if not rows:
        raise ResourceNotFoundError("No decision summary is available yet.")
    return DecisionSummaryResponse(**rows[0])
