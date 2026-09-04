from typing import Optional

from fastapi import APIRouter, Query

from backend.models.revenue import RevenueForecastResponse, RevenueTrendsResponse
from backend.services.revenue_service import get_revenue_forecast, get_revenue_trends

router = APIRouter(prefix="/revenue", tags=["revenue"])


@router.get("/trends", response_model=RevenueTrendsResponse)
def read_revenue_trends(
    period: Optional[str] = Query(None, description="daily, monthly (default), quarterly, or yearly"),
    region: Optional[str] = Query(None),
    service: Optional[str] = Query(None, description="Accepted for interface consistency; VW_REVENUE_TRENDS has no service dimension (see docs/api_reference.md), so this filter currently has no effect"),
    segment: Optional[str] = Query(None),
):
    return get_revenue_trends(period, region, segment)


@router.get("/forecast", response_model=RevenueForecastResponse)
def read_revenue_forecast():
    return get_revenue_forecast()
