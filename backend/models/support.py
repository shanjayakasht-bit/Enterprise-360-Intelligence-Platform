from typing import Optional

from pydantic import BaseModel


class SupportMetricsResponse(BaseModel):
    total_tickets: int
    open_tickets: int
    high_priority_tickets: int
    sla_breaches: int
    avg_resolution_time_hours: Optional[float] = None
    avg_satisfaction_rating: Optional[float] = None
