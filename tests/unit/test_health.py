from fastapi.testclient import TestClient

from ai_gateway.main import create_app


def test_health_returns_ready() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
