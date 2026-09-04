from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_shape():
    body = client.get("/api/v1/health").json()
    assert body["status"] in ("healthy", "degraded")
    assert body["service"] == "NEXORA API"
    assert body["snowflake"] in ("connected", "unavailable")
    assert body["version"] == "1.0.0"


def test_health_never_exposes_credentials():
    body = client.get("/api/v1/health").json()
    serialized = str(body).lower()
    for secret_marker in ("password", "snowflake_password"):
        assert secret_marker not in serialized
