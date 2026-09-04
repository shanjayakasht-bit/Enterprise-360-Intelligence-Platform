"""Shared pagination helpers -- every paginated endpoint uses LIMIT/OFFSET
computed here and a COUNT(*) query (with the same filters) for total_items,
never loading a full table into Python to paginate in memory.
"""

from dataclasses import dataclass

from fastapi import Query

from backend.core.config import settings


@dataclass
class Pagination:
    page: int
    page_size: int

    @property
    def limit(self):
        return self.page_size

    @property
    def offset(self):
        return (self.page - 1) * self.page_size


def pagination_params(
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size, description="Rows per page"),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


def build_page_info(pagination: Pagination, total_items: int) -> dict:
    total_pages = (total_items + pagination.page_size - 1) // pagination.page_size if pagination.page_size else 0
    return {
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total_items": total_items,
        "total_pages": total_pages,
    }
