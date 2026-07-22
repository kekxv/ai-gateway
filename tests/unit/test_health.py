import pytest
from fastapi.testclient import TestClient

from ai_gateway.main import create_app


def test_health_without_lifespan_or_settings_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_settings_load() -> None:
        pytest.fail("health without an initialized engine must not load application secrets")

    monkeypatch.setattr("ai_gateway.main.get_settings", forbidden_settings_load)
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
