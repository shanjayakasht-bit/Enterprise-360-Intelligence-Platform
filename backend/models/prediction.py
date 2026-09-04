from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CustomerRiskPredictionRow(BaseModel):
    customer_id: str
    risk_probability: Optional[float] = None
    predicted_class: Optional[int] = None
    risk_level: Optional[str] = None
    model_version: str
    generated_at: datetime


class ProjectRiskPredictionRow(BaseModel):
    project_id: str
    risk_probability: Optional[float] = None
    predicted_risk_class: Optional[int] = None
    risk_level: Optional[str] = None
    model_version: str
    generated_at: datetime


class PaymentDelayPredictionRow(BaseModel):
    invoice_id: str
    customer_id: str
    delay_probability: Optional[float] = None
    predicted_delay: Optional[int] = None
    risk_level: Optional[str] = None
    model_version: str
    generated_at: datetime
