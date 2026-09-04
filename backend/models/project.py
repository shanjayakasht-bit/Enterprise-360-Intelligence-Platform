from datetime import date
from typing import List, Optional

from pydantic import BaseModel

from backend.models.decision import DecisionRef


class ProjectRiskCard(BaseModel):
    project_id: str
    customer_id: str
    company_name: str
    department_name: Optional[str] = None
    project_manager_name: Optional[str] = None
    status: str
    budget: Optional[float] = None
    actual_cost: Optional[float] = None
    completion_pct: Optional[float] = None
    project_risk_category: Optional[str] = None
    days_to_deadline: Optional[int] = None
    risk_probability: Optional[float] = None
    risk_level: Optional[str] = None


class ProjectRiskPrediction(BaseModel):
    risk_probability: Optional[float] = None
    predicted_risk_class: Optional[int] = None
    risk_level: Optional[str] = None
    model_version: Optional[str] = None


class ProjectDetail(BaseModel):
    project_id: str
    customer_id: str
    company_name: str
    department_name: Optional[str] = None
    project_manager_id: Optional[str] = None
    project_manager_name: Optional[str] = None
    status: str
    budget: Optional[float] = None
    actual_cost: Optional[float] = None
    cost_variance: Optional[float] = None
    budget_utilization_pct: Optional[float] = None
    cost_overrun_pct: Optional[float] = None
    completion_pct: Optional[float] = None
    project_risk_score: Optional[float] = None
    project_risk_category: Optional[str] = None
    planned_end_date: Optional[date] = None
    days_to_deadline: Optional[int] = None
    risk_prediction: ProjectRiskPrediction
    active_decisions: List[DecisionRef]
