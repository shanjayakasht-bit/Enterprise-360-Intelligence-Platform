from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_customers_list_returns_200():
    response = client.get("/api/v1/customers?page=1&page_size=5")
    assert response.status_code == 200


def test_customers_list_paginates():
    body = client.get("/api/v1/customers?page=1&page_size=5").json()
    assert len(body["items"]) == 5
    assert body["page_info"]["page"] == 1
    assert body["page_info"]["page_size"] == 5
    assert body["page_info"]["total_items"] > 5000 - 1  # full customer population
    assert body["page_info"]["total_pages"] > 1


def test_customers_list_shape():
    item = client.get("/api/v1/customers?page_size=1").json()["items"][0]
    for field in ("customer_id", "company_name", "segment", "region"):
        assert field in item


def test_customers_invalid_risk_level_returns_400():
    response = client.get("/api/v1/customers?risk_level=NotARealLevel")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_filter"


def test_customer_detail_by_valid_id():
    first_id = client.get("/api/v1/customers?page_size=1").json()["items"][0]["customer_id"]
    response = client.get(f"/api/v1/customers/{first_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["customer_id"] == first_id
    for section in ("profile", "revenue", "subscriptions", "projects", "finance", "support", "activity", "segment", "risk_prediction", "active_decisions"):
        assert section in body


def test_customer_detail_unknown_id_returns_404():
    response = client.get("/api/v1/customers/CUST_DOES_NOT_EXIST")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "resource_not_found"
