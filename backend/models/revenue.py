from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class RevenueTrendPoint(BaseModel):
    period_start: date
    period_label: Optional[str] = None
    deal_revenue: Optional[float] = None
    subscription_mrr_booked: Optional[float] = None
    subscription_arr_booked: Optional[float] = None
    invoice_amount: Optional[float] = None
    payments_received: Optional[float] = None


class RevenueTrendsResponse(BaseModel):
    period: str
    points: List[RevenueTrendPoint]


class RevenueForecastPoint(BaseModel):
    forecast_date: date
    predicted_revenue: float
    lower_bound: float
    upper_bound: float
    model_version: str
    generated_at: datetime


class RevenueHistoricalPoint(BaseModel):
    month: date
    invoice_amount: float


class RevenueForecastResponse(BaseModel):
    historical_context: List[RevenueHistoricalPoint]
    forecast: List[RevenueForecastPoint]
