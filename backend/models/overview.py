from typing import Optional

from pydantic import BaseModel


class OverviewResponse(BaseModel):
    total_revenue: Optional[float] = None
    active_customers: Optional[int] = None
    active_subscriptions: Optional[int] = None
    active_projects: Optional[int] = None
    projects_at_risk: Optional[int] = None
    open_support_tickets: Optional[int] = None
    support_sla_percentage: Optional[float] = None
    average_customer_health: Optional[float] = None
    total_invoice_amount: Optional[float] = None
    total_payments_received: Optional[float] = None
    outstanding_amount: Optional[float] = None
    enterprise_health_score: Optional[float] = None

    critical_decisions: Optional[int] = None
    high_priority_decisions: Optional[int] = None
    customers_at_risk: Optional[int] = None
    revenue_at_risk: Optional[float] = None
    payment_value_at_risk: Optional[float] = None
    revenue_opportunity_value: Optional[float] = None
