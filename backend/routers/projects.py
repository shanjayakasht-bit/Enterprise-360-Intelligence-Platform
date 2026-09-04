from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.models.common import PageInfo, PaginatedResponse
from backend.models.project import ProjectDetail, ProjectRiskCard
from backend.services.project_service import get_project_detail, list_project_risk
from backend.utils.pagination import Pagination, pagination_params

router = APIRouter(prefix="/projects", tags=["projects"])


# NOTE: /risk must be declared before /{project_id} so it isn't captured
# as a project_id path parameter.
@router.get("/risk", response_model=PaginatedResponse[ProjectRiskCard])
def read_project_risk(
    pagination: Pagination = Depends(pagination_params),
    risk_level: Optional[str] = Query(None, description="Low, Medium, or High"),
    department: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
):
    items, page_info = list_project_risk(pagination, risk_level, department, customer_id)
    return PaginatedResponse(items=items, page_info=PageInfo(**page_info))


@router.get("/{project_id}", response_model=ProjectDetail)
def read_project_detail(project_id: str):
    return get_project_detail(project_id)
