import pytest

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import CanonicalRequest


def test_systemone_round_trips_typed_request_without_losing_questions() -> None:
    payload = {
        "model": "jev-latest",
        "state": {"ticket": "payout failed"},
        "questions": {
            "urgent": {"type": "noul", "instructions": "Is this urgent?"},
            "team": {
                "type": "choice",
                "instructions": "Who owns this?",
                "criteria": {"billing": None},
            },
        },
    }
    adapter = get_adapter(Protocol.SYSTEMONE)
    request = adapter.decode_request(payload)
    assert isinstance(request, CanonicalRequest)
    assert adapter.encode_request(request) == payload


def test_systemone_rejects_streaming() -> None:
    with pytest.raises(Exception, match="does not support streaming"):
        get_adapter(Protocol.SYSTEMONE).decode_request(
            {
                "model": "jev-latest",
                "state": "x",
                "stream": True,
                "questions": {"q": {"type": "noul", "instructions": "?"}},
            }
        )
