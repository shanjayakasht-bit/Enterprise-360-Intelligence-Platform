"""Serves existing Phase 4 model predictions only -- no model is trained or
scored inside a request; every response is a straight read from the
already-populated ML_* tables."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from backend.models.common import PageInfo, PaginatedResponse
from backend.models.prediction import (
    CustomerRiskPredictionRow, PaymentDelayPredictionRow, ProjectRiskPredictionRow,
)
from backend.models.revenue import RevenueForecastPoint
from backend.services.prediction_service import list_predictions, list_revenue_predictions
from backend.utils.pagination import Pagination, pagination_params

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/customers", response_model=PaginatedResponse[CustomerRiskPredictionRow])
def read_customer_predictions(
    pagination: Pagination = Depends(pagination_params),
    risk_level: Optional[str] = Query(None, description="Low, Medium, or High"),
):
    items, page_info = list_predictions("customers", pagination, risk_level)
    return PaginatedResponse(items=items, page_info=PageInfo(**page_info))


@router.get("/projects", response_model=PaginatedResponse[ProjectRiskPredictionRow])
def read_project_predictions(
    pagination: Pagination = Depends(pagination_params),
    risk_level: Optional[str] = Query(None, description="Low, Medium, or High"),
):
    items, page_info = list_predictions("projects", pagination, risk_level)
    return PaginatedResponse(items=items, page_info=PageInfo(**page_info))


@router.get("/payments", response_model=PaginatedResponse[PaymentDelayPredictionRow])
def read_payment_predictions(
    pagination: Pagination = Depends(pagination_params),
    risk_level: Optional[str] = Query(None, description="Low, Medium, or High"),
):
    items, page_info = list_predictions("payments", pagination, risk_level)
    return PaginatedResponse(items=items, page_info=PageInfo(**page_info))


@router.get("/revenue", response_model=List[RevenueForecastPoint])
def read_revenue_predictions():
    return list_revenue_predictions()
