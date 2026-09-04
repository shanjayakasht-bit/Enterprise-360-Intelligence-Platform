from backend.core.exceptions import ResourceNotFoundError
from backend.db.queries import (
    PROJECT_DECISIONS_SQL, PROJECT_DETAIL_SQL, project_risk_count_query, project_risk_list_query,
)
from backend.db.snowflake import execute_query
from backend.models.decision import DecisionRef
from backend.models.project import ProjectDetail, ProjectRiskCard, ProjectRiskPrediction
from backend.utils.pagination import Pagination, build_page_info


def list_project_risk(pagination: Pagination, risk_level, department, customer_id):
    sql, params = project_risk_list_query(risk_level, department, customer_id, pagination.limit, pagination.offset)
    rows = execute_query(sql, params=params, operation="projects_risk_list")

    count_sql, count_params = project_risk_count_query(risk_level, department, customer_id)
    total = execute_query(count_sql, params=count_params, operation="projects_risk_count")[0]["total"]

    items = [ProjectRiskCard(**row) for row in rows]
    return items, build_page_info(pagination, total)


def get_project_detail(project_id: str) -> ProjectDetail:
    rows = execute_query(PROJECT_DETAIL_SQL, params=[project_id], operation="project_detail")
    if not rows:
        raise ResourceNotFoundError(f"Project '{project_id}' was not found.")
    row = rows[0]

    decision_rows = execute_query(PROJECT_DECISIONS_SQL, params=[project_id], operation="project_decisions")

    return ProjectDetail(
        project_id=row["project_id"], customer_id=row["customer_id"], company_name=row["company_name"],
        department_name=row.get("department_name"), project_manager_id=row.get("project_manager_id"),
        project_manager_name=row.get("project_manager_name"), status=row["status"], budget=row.get("budget"),
        actual_cost=row.get("actual_cost"), cost_variance=row.get("cost_variance"),
        budget_utilization_pct=row.get("budget_utilization_pct"), cost_overrun_pct=row.get("cost_overrun_pct"),
        completion_pct=row.get("completion_pct"), project_risk_score=row.get("project_risk_score"),
        project_risk_category=row.get("project_risk_category"), planned_end_date=row.get("planned_end_date"),
        days_to_deadline=row.get("days_to_deadline"),
        risk_prediction=ProjectRiskPrediction(
            risk_probability=row.get("risk_probability"), predicted_risk_class=row.get("predicted_risk_class"),
            risk_level=row.get("ml_risk_level"), model_version=row.get("ml_model_version"),
        ),
        active_decisions=[DecisionRef(**d) for d in decision_rows],
    )
