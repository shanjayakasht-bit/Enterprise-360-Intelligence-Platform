from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_decisions_list_returns_200():
    response = client.get("/api/v1/decisions?page_size=10")
    assert response.status_code == 200


def test_decisions_sorted_by_priority_desc():
    items = client.get("/api/v1/decisions?page_size=25").json()["items"]
    scores = [item["priority_score"] for item in items]
    assert scores == sorted(scores, reverse=True)


def test_decisions_shape():
    item = client.get("/api/v1/decisions?page_size=1").json()["items"][0]
    for field in (
        "decision_id", "title", "summary", "severity", "priority_score", "entity_type", "entity_id",
        "what_happened", "why_it_happened", "predicted_outcome", "business_impact", "confidence",
        "recommended_actions", "status", "generated_at",
    ):
        assert field in item
    assert item["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert 0 <= item["priority_score"] <= 100
    assert isinstance(item["recommended_actions"], list) and len(item["recommended_actions"]) >= 1


def test_decisions_filter_by_severity():
    body = client.get("/api/v1/decisions?severity=CRITICAL&page_size=25").json()
    assert all(item["severity"] == "CRITICAL" for item in body["items"])


def test_decisions_invalid_severity_returns_400():
    response = client.get("/api/v1/decisions?severity=SUPER_CRITICAL")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_filter"


def test_decision_detail_by_valid_id():
    first_id = client.get("/api/v1/decisions?page_size=1").json()["items"][0]["decision_id"]
    response = client.get(f"/api/v1/decisions/{first_id}")
    assert response.status_code == 200
    assert response.json()["decision_id"] == first_id


def test_decision_detail_unknown_id_returns_404():
    response = client.get("/api/v1/decisions/DOES_NOT_EXIST")
    assert response.status_code == 404


def test_decisions_summary_returns_200_and_shape():
    response = client.get("/api/v1/decisions/summary")
    assert response.status_code == 200
    body = response.json()
    for field in (
        "critical_decisions", "high_priority_decisions", "customers_at_risk", "revenue_at_risk",
        "projects_at_risk", "payment_value_at_risk", "revenue_opportunity_value", "generated_at",
    ):
        assert field in body
