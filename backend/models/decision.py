from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class DecisionRef(BaseModel):
    """Lightweight decision reference, embedded in customer/project detail
    responses ("associated decisions") -- the full card is available via
    GET /api/v1/decisions/{decision_id}."""

    decision_id: str
    decision_type: str
    title: str
    severity: str
    priority_score: float
    status: str
    generated_at: datetime


class BusinessImpact(BaseModel):
    type: Optional[str] = None
    value: Optional[float] = None


class DecisionCard(BaseModel):
    decision_id: str
    decision_type: str
    entity_type: str
    entity_id: str
    title: str
    summary: Optional[str] = None
    severity: str
    priority_score: float
    what_happened: str
    why_it_happened: str
    predicted_outcome: Optional[str] = None
    business_impact: BusinessImpact
    confidence: Optional[float] = None
    recommended_actions: List[str]
    status: str
    generated_at: datetime

    @classmethod
    def from_row(cls, row):
        actions = [
            row.get(f"recommended_action_{i}")
            for i in range(1, 6)
            if row.get(f"recommended_action_{i}")
        ]
        return cls(
            decision_id=row["decision_id"],
            decision_type=row["decision_type"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            title=row["title"],
            summary=row.get("summary"),
            severity=row["severity"],
            priority_score=row["priority_score"],
            what_happened=row["what_happened"],
            why_it_happened=row["why_it_happened"],
            predicted_outcome=row.get("predicted_outcome"),
            business_impact=BusinessImpact(type=row.get("business_impact_type"), value=row.get("business_impact_value")),
            confidence=row.get("confidence_score"),
            recommended_actions=actions,
            status=row["status"],
            generated_at=row["generated_at"],
        )


class DecisionSummaryResponse(BaseModel):
    critical_decisions: int
    high_priority_decisions: int
    customers_at_risk: int
    revenue_at_risk: float
    projects_at_risk: int
    payment_value_at_risk: float
    revenue_opportunity_value: float
    generated_at: datetime
