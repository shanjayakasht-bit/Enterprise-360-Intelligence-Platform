from typing import Optional

from fastapi import APIRouter, Query

from backend.models.support import SupportMetricsResponse
from backend.services.support_service import get_support_metrics

router = APIRouter(prefix="/support", tags=["support"])


@router.get("", response_model=SupportMetricsResponse)
def read_support_metrics(
    priority: Optional[str] = Query(None, description="Low, Medium, High, or Critical"),
    status: Optional[str] = Query(None, description="Open, In Progress, Resolved, Closed, or Escalated"),
    customer_id: Optional[str] = Query(None),
):
    return get_support_metrics(priority, status, customer_id)
