from __future__ import annotations

import pytest

from ai_gateway.protocols.gemini import GeminiAdapter


def test_gemini_golden_request_round_trips(load_fixture) -> None:
    adapter = GeminiAdapter()
    canonical = adapter.decode_request(load_fixture("gemini", "request.json"))
    decoded_again = adapter.decode_request(adapter.encode_request(canonical))

    assert decoded_again == canonical
    assert canonical.tool_choice == "required"
    assert canonical.stop_sequences == ("END", "STOP")
    assert canonical.metadata["vendor_extensions"]["gemini"] == {
        "cachedContent": "cachedContents/example"
    }


@pytest.mark.parametrize(
    ("native", "canonical"),
    [
        ("STOP", "stop"),
        ("MAX_TOKENS", "length"),
        ("SAFETY", "content_filter"),
        ("MALFORMED_FUNCTION_CALL", "error"),
    ],
)
def test_gemini_finish_reasons(native: str, canonical: str, load_fixture) -> None:
    payload = load_fixture("gemini", "response.json")
    payload["candidates"][0]["finishReason"] = native
    payload["candidates"][0]["content"]["parts"] = [{"text": "Done."}]
    assert GeminiAdapter().decode_response(payload).finish_reason == canonical


def test_gemini_function_call_stop_is_normalized_to_tool_call(load_fixture) -> None:
    payload = load_fixture("gemini", "response.json")
    assert GeminiAdapter().decode_response(payload).finish_reason == "tool_call"


def test_gemini_golden_response_and_stream(load_fixture, load_bytes) -> None:
    adapter = GeminiAdapter()
    response = adapter.decode_response(load_fixture("gemini", "response.json"))
    event = adapter.decode_stream_event(load_bytes("gemini", "stream.sse"))

    assert response.usage is not None
    assert response.usage.output_tokens == 7
    assert event.type == "content_delta"
    assert event.text == "Hello"
    assert adapter.decode_stream_event(adapter.encode_stream_event(event)) == event
