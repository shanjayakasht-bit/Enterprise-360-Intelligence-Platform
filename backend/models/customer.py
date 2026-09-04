from datetime import date
from typing import List, Optional

from pydantic import BaseModel

from backend.models.decision import DecisionRef


class CustomerCard(BaseModel):
    """Summarized card for GET /api/v1/customers list rows."""

    customer_id: str
    company_name: str
    segment: Optional[str] = None
    region: Optional[str] = None
    industry: Optional[str] = None
    total_revenue: Optional[float] = None
    arr: Optional[float] = None
    customer_health_score: Optional[float] = None
    customer_status: Optional[str] = None
    risk_probability: Optional[float] = None
    risk_level: Optional[str] = None
    cluster_segment_name: Optional[str] = None


class CustomerProfile(BaseModel):
    customer_id: str
    company_name: str
    segment: Optional[str] = None
    region: Optional[str] = None
    industry: Optional[str] = None
    customer_status: Optional[str] = None
    customer_health_score: Optional[float] = None
    renewal_date: Optional[date] = None
    days_to_renewal: Optional[int] = None


class CustomerRevenue(BaseModel):
    total_deal_value: Optional[float] = None
    won_deal_value: Optional[float] = None
    total_revenue: Optional[float] = None
    arr: Optional[float] = None
    mrr: Optional[float] = None


class CustomerSubscriptions(BaseModel):
    active_subscriptions: Optional[int] = None
    arr: Optional[float] = None
    mrr: Optional[float] = None


class CustomerProjects(BaseModel):
    project_count: Optional[int] = None
    delayed_projects: Optional[int] = None
    project_risk: Optional[float] = None


class CustomerFinance(BaseModel):
    invoice_total: Optional[float] = None
    payments_received: Optional[float] = None
    outstanding_amount: Optional[float] = None
    average_payment_delay: Optional[float] = None


class CustomerSupport(BaseModel):
    support_ticket_count: Optional[int] = None
    open_ticket_count: Optional[int] = None
    sla_breaches: Optional[int] = None
    average_support_satisfaction: Optional[float] = None


class CustomerActivity(BaseModel):
    activity_count: Optional[int] = None
    average_usage_score: Optional[float] = None
    recent_activity_date: Optional[date] = None


class CustomerSegmentInfo(BaseModel):
    churn_risk_score: Optional[float] = None
    churn_risk_category: Optional[str] = None
    cluster_id: Optional[int] = None
    cluster_segment_name: Optional[str] = None
    distance_from_centroid: Optional[float] = None


class CustomerRiskPrediction(BaseModel):
    risk_probability: Optional[float] = None
    predicted_class: Optional[int] = None
    risk_level: Optional[str] = None
    model_version: Optional[str] = None


class CustomerDetail(BaseModel):
    profile: CustomerProfile
    revenue: CustomerRevenue
    subscriptions: CustomerSubscriptions
    projects: CustomerProjects
    finance: CustomerFinance
    support: CustomerSupport
    activity: CustomerActivity
    segment: CustomerSegmentInfo
    risk_prediction: CustomerRiskPrediction
    active_decisions: List[DecisionRef]
