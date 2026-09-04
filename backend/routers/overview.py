from fastapi import APIRouter

from backend.models.overview import OverviewResponse
from backend.services.overview_service import get_overview

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def read_overview():
    return get_overview()
