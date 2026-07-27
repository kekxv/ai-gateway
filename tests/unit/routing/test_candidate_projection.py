from ai_gateway.core.enums import Protocol, RouteRuntimeState
from ai_gateway.routing.service import _candidate_from_row


def test_route_candidate_preserves_explicit_responses_capability() -> None:
    candidate = _candidate_from_row(
        {
            "route_id": 1,
            "model_id": 2,
            "provider_id": 3,
            "provider_protocol_id": 4,
            "protocol": Protocol.OPENAI.value,
            "base_url": "https://legacy-openai.example/v1",
            "websocket_url": None,
            "supports_responses": False,
            "upstream_model": "gpt-4.1-mini",
            "weight": 100,
            "runtime_state": RouteRuntimeState.CLOSED.value,
            "disabled_until": None,
            "provider_credential_encrypted": b"secret",
            "extra_headers_encrypted": None,
        }
    )

    assert candidate.supports_responses is False
