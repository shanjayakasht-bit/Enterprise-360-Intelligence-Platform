from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_overview_returns_200():
    response = client.get("/api/v1/overview")
    assert response.status_code == 200


def test_overview_kpis_not_null():
    body = client.get("/api/v1/overview").json()
    for field in ("total_revenue", "active_customers", "enterprise_health_score", "critical_decisions"):
        assert body[field] is not None, f"{field} was unexpectedly null"


def test_overview_values_are_plausible():
    body = client.get("/api/v1/overview").json()
    assert body["total_revenue"] >= 0
    assert body["active_customers"] >= 0
    assert 0 <= body["enterprise_health_score"] <= 100
