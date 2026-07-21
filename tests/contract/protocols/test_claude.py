from __future__ import annotations

import pytest

from ai_gateway.protocols.base import UnsupportedFeatureError
from ai_gateway.protocols.claude import ClaudeAdapter
from ai_gateway.protocols.types import CanonicalMessage, CanonicalRequest, TextPart, ToolResultPart


def test_claude_golden_request_round_trips(load_fixture) -> None:
    adapter = ClaudeAdapter()
    canonical = adapter.decode_request(load_fixture("claude", "request.json"))
    decoded_again = adapter.decode_request(adapter.encode_request(canonical))

    assert decoded_again == canonical
    assert canonical.max_output_tokens == 128
    assert canonical.metadata["vendor_extensions"]["claude"]["service_tier"] == "auto"


@pytest.mark.parametrize(
    ("native", "canonical"),
    [
        ("end_turn", "stop"),
        ("max_tokens", "length"),
        ("tool_use", "tool_call"),
        ("refusal", "content_filter"),
    ],
)
def test_claude_finish_reasons(native: str, canonical: str, load_fixture) -> None:
    payload = load_fixture("claude", "response.json")
    payload["stop_reason"] = native
    assert ClaudeAdapter().decode_response(payload).finish_reason == canonical


def test_claude_golden_response_and_stream(load_fixture, load_bytes) -> None:
    adapter = ClaudeAdapter()
    response = adapter.decode_response(load_fixture("claude", "response.json"))
    events = adapter.decode_stream_event(load_bytes("claude", "stream.sse"))

    assert response.finish_reason == "tool_call"
    assert response.usage is not None
    assert response.usage.input_tokens == 42
    assert events == (events[0],)
    assert events[0].type == "content_delta"
    assert events[0].text == "Hello"
    assert adapter.decode_stream_event(adapter.encode_stream_event(events[0])) == events


def test_impossible_tool_result_conversion_is_422_and_names_field() -> None:
    request = CanonicalRequest(
        model="model",
        messages=(
            CanonicalMessage(
                role="user",
                content=(ToolResultPart(tool_call_id=None, name=None, content=(TextPart("x"),)),),
            ),
        ),
        system=(),
        tools=(),
        tool_choice=None,
        temperature=None,
        top_p=None,
        max_output_tokens=1,
        stop_sequences=(),
        stream=False,
        metadata={},
    )

    with pytest.raises(UnsupportedFeatureError) as exc_info:
        ClaudeAdapter().encode_request(request)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "unsupported_feature"
    assert "tool_call_id" in exc_info.value.message
