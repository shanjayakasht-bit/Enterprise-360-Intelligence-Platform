from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.models.common import PageInfo, PaginatedResponse
from backend.models.decision import DecisionCard, DecisionSummaryResponse
from backend.services.decision_service import get_decision_detail, get_decision_summary, list_decisions
from backend.utils.pagination import Pagination, pagination_params

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.get("", response_model=PaginatedResponse[DecisionCard])
def read_decisions(
    pagination: Pagination = Depends(pagination_params),
    severity: Optional[str] = Query(None, description="LOW, MEDIUM, HIGH, or CRITICAL"),
    decision_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="NEW, ACKNOWLEDGED, IN_PROGRESS, RESOLVED, or DISMISSED"),
):
    items, page_info = list_decisions(pagination, severity, decision_type, entity_type, status)
    return PaginatedResponse(items=items, page_info=PageInfo(**page_info))


# NOTE: /summary must be declared before /{decision_id} so it isn't
# captured as a decision_id path parameter.
@router.get("/summary", response_model=DecisionSummaryResponse)
def read_decision_summary():
    return get_decision_summary()


@router.get("/{decision_id}", response_model=DecisionCard)
def read_decision_detail(decision_id: str):
    return get_decision_detail(decision_id)
