from __future__ import annotations

import pytest

from ai_gateway.protocols.claude import ClaudeAdapter
from ai_gateway.protocols.gemini import GeminiAdapter
from ai_gateway.protocols.openai import OpenAIAdapter


def test_gemini_golden_request_round_trips(load_fixture) -> None:
    adapter = GeminiAdapter()
    canonical = adapter.decode_request(load_fixture("gemini", "request.json"))
    decoded_again = adapter.decode_request(adapter.encode_request(canonical))

    assert decoded_again == canonical
    assert canonical.tool_choice == {"name": "weather"}
    assert canonical.stop_sequences == ("END", "STOP")
    assert canonical.metadata["vendor_extensions"]["gemini"]["cachedContent"] == (
        "cachedContents/example"
    )


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


def test_gemini_blocked_prompt_decodes_as_empty_content_filter_response() -> None:
    response = GeminiAdapter().decode_response(
        {
            "modelVersion": "gemini-test",
            "promptFeedback": {
                "blockReason": "SAFETY",
                "safetyRatings": [{"category": "HARM_CATEGORY_DANGEROUS_CONTENT"}],
            },
            "usageMetadata": {"promptTokenCount": 3, "totalTokenCount": 3},
        }
    )

    assert response.finish_reason == "content_filter"
    assert response.message.content == ()
    assert response.usage is not None
    assert response.usage.input_tokens == 3
    assert response.metadata["vendor_extensions"]["gemini"]["promptFeedback"] == {
        "blockReason": "SAFETY",
        "safetyRatings": ({"category": "HARM_CATEGORY_DANGEROUS_CONTENT"},),
    }


def test_gemini_safety_candidate_without_content_decodes_and_cross_encodes() -> None:
    response = GeminiAdapter().decode_response(
        {
            "modelVersion": "gemini-test",
            "candidates": [
                {
                    "index": 0,
                    "finishReason": "SAFETY",
                    "safetyRatings": [{"category": "HARM_CATEGORY_HARASSMENT"}],
                }
            ],
        }
    )

    assert response.finish_reason == "content_filter"
    assert response.message.content == ()
    assert response.metadata["vendor_extensions"]["gemini"]["__candidate__"] == {
        "safetyRatings": ({"category": "HARM_CATEGORY_HARASSMENT"},),
    }
    assert OpenAIAdapter().encode_response(response)["choices"][0]["message"]["content"] is None
    assert ClaudeAdapter().encode_response(response)["content"] == []


def test_gemini_golden_response_and_stream(load_fixture, load_bytes) -> None:
    adapter = GeminiAdapter()
    response = adapter.decode_response(load_fixture("gemini", "response.json"))
    events = adapter.decode_stream_event(load_bytes("gemini", "stream.sse"))

    assert response.usage is not None
    assert response.usage.output_tokens == 7
    content = next(event for event in events if event.type == "content_delta")
    assert content.text == "Hello"
    encoded = adapter.create_stream_encoder().encode(content)
    decoded = tuple(
        item for frame in encoded for item in adapter.create_stream_decoder().decode(frame)
    )
    assert next(event for event in decoded if event.type == "content_delta").text == "Hello"
