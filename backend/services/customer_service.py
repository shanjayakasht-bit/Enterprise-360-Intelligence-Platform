from backend.core.exceptions import ResourceNotFoundError
from backend.db.queries import (
    CUSTOMER_DECISIONS_SQL, CUSTOMER_DETAIL_SQL, customer_count_query, customer_list_query,
)
from backend.db.snowflake import execute_query
from backend.models.customer import (
    CustomerActivity, CustomerCard, CustomerDetail, CustomerFinance, CustomerProfile,
    CustomerProjects, CustomerRevenue, CustomerRiskPrediction, CustomerSegmentInfo,
    CustomerSubscriptions, CustomerSupport,
)
from backend.models.decision import DecisionRef
from backend.utils.pagination import Pagination, build_page_info


def list_customers(pagination: Pagination, region, segment, risk_level, search):
    sql, params = customer_list_query(region, segment, risk_level, search, pagination.limit, pagination.offset)
    rows = execute_query(sql, params=params, operation="customers_list")

    count_sql, count_params = customer_count_query(region, segment, risk_level, search)
    total = execute_query(count_sql, params=count_params, operation="customers_count")[0]["total"]

    items = [CustomerCard(**row) for row in rows]
    return items, build_page_info(pagination, total)


def get_customer_detail(customer_id: str) -> CustomerDetail:
    rows = execute_query(CUSTOMER_DETAIL_SQL, params=[customer_id], operation="customer_detail")
    if not rows:
        raise ResourceNotFoundError(f"Customer '{customer_id}' was not found.")
    row = rows[0]

    decision_rows = execute_query(CUSTOMER_DECISIONS_SQL, params=[customer_id], operation="customer_decisions")

    return CustomerDetail(
        profile=CustomerProfile(
            customer_id=row["customer_id"], company_name=row["company_name"], segment=row.get("segment"),
            region=row.get("region"), industry=row.get("industry"), customer_status=row.get("customer_status"),
            customer_health_score=row.get("customer_health_score"), renewal_date=row.get("renewal_date"),
            days_to_renewal=row.get("days_to_renewal"),
        ),
        revenue=CustomerRevenue(
            total_deal_value=row.get("total_deal_value"), won_deal_value=row.get("won_deal_value"),
            total_revenue=row.get("total_revenue"), arr=row.get("arr"), mrr=row.get("mrr"),
        ),
        subscriptions=CustomerSubscriptions(
            active_subscriptions=row.get("active_subscriptions"), arr=row.get("arr"), mrr=row.get("mrr"),
        ),
        projects=CustomerProjects(
            project_count=row.get("project_count"), delayed_projects=row.get("delayed_projects"),
            project_risk=row.get("project_risk"),
        ),
        finance=CustomerFinance(
            invoice_total=row.get("invoice_total"), payments_received=row.get("payments_received"),
            outstanding_amount=row.get("outstanding_amount"), average_payment_delay=row.get("average_payment_delay"),
        ),
        support=CustomerSupport(
            support_ticket_count=row.get("support_ticket_count"), open_ticket_count=row.get("open_ticket_count"),
            sla_breaches=row.get("sla_breaches"), average_support_satisfaction=row.get("average_support_satisfaction"),
        ),
        activity=CustomerActivity(
            activity_count=row.get("activity_count"), average_usage_score=row.get("average_usage_score"),
            recent_activity_date=row.get("recent_activity_date"),
        ),
        segment=CustomerSegmentInfo(
            churn_risk_score=row.get("churn_risk_score"), churn_risk_category=row.get("churn_risk_category"),
            cluster_id=row.get("cluster_id"), cluster_segment_name=row.get("cluster_segment_name"),
            distance_from_centroid=row.get("distance_from_centroid"),
        ),
        risk_prediction=CustomerRiskPrediction(
            risk_probability=row.get("risk_probability"), predicted_class=row.get("predicted_class"),
            risk_level=row.get("ml_risk_level"), model_version=row.get("ml_model_version"),
        ),
        active_decisions=[DecisionRef(**d) for d in decision_rows],
    )
