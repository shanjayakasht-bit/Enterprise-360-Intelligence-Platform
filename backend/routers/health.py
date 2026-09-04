from fastapi import APIRouter

from backend.core.config import settings
from backend.db.snowflake import health_check
from backend.models.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health():
    connected = health_check()
    return HealthResponse(
        status="healthy" if connected else "degraded",
        service=settings.app_name,
        snowflake="connected" if connected else "unavailable",
        version=settings.app_version,
    )
