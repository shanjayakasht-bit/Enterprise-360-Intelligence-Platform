"""Small reference-value endpoints that populate dashboard filter dropdowns
(region/segment/service/department pickers). Deliberately thin -- no
dedicated service module, since each is a single small, static query
straight from a CORE dimension or ANALYTICS view."""

from typing import List

from fastapi import APIRouter

from backend.db.queries import (
    METADATA_DEPARTMENTS_SQL, METADATA_REGIONS_SQL, METADATA_SEGMENTS_SQL, METADATA_SERVICES_SQL,
)
from backend.db.snowflake import execute_query

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/regions", response_model=List[str])
def read_regions():
    rows = execute_query(METADATA_REGIONS_SQL, operation="metadata_regions")
    return [r["region_name"] for r in rows]


@router.get("/services", response_model=List[dict])
def read_services():
    rows = execute_query(METADATA_SERVICES_SQL, operation="metadata_services")
    return rows


@router.get("/segments", response_model=List[str])
def read_segments():
    rows = execute_query(METADATA_SEGMENTS_SQL, operation="metadata_segments")
    return [r["segment"] for r in rows]


@router.get("/departments", response_model=List[str])
def read_departments():
    rows = execute_query(METADATA_DEPARTMENTS_SQL, operation="metadata_departments")
    return [r["department_name"] for r in rows]
