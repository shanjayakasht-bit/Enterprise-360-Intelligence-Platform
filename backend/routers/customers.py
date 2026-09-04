from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.models.common import PageInfo, PaginatedResponse
from backend.models.customer import CustomerCard, CustomerDetail
from backend.services.customer_service import get_customer_detail, list_customers
from backend.utils.pagination import Pagination, pagination_params

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=PaginatedResponse[CustomerCard])
def read_customers(
    pagination: Pagination = Depends(pagination_params),
    region: Optional[str] = Query(None),
    segment: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None, description="Low, Medium, or High"),
    search: Optional[str] = Query(None, description="Matches company name or customer_id"),
):
    items, page_info = list_customers(pagination, region, segment, risk_level, search)
    return PaginatedResponse(items=items, page_info=PageInfo(**page_info))


@router.get("/{customer_id}", response_model=CustomerDetail)
def read_customer_detail(customer_id: str):
    return get_customer_detail(customer_id)
