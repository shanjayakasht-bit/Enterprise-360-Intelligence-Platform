from backend.db.queries import OVERVIEW_SQL
from backend.db.snowflake import execute_query
from backend.models.overview import OverviewResponse


def get_overview() -> OverviewResponse:
    rows = execute_query(OVERVIEW_SQL, operation="overview")
    if not rows:
        return OverviewResponse()
    return OverviewResponse(**rows[0])
