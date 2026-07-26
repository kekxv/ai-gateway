from __future__ import annotations

from dataclasses import FrozenInstanceError

import orjson
import pytest

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import rewrite_passthrough_request, rewrite_passthrough_sse
from ai_gateway.protocols.openai import OpenAIAdapter
from ai_gateway.protocols.types import ImagePart, TextPart, ToolCallPart, ToolResultPart


def test_openai_golden_request_decodes_all_contract_fields(load_fixture) -> None:
    canonical = OpenAIAdapter().decode_request(load_fixture("openai", "request.json"))

    assert canonical.model == "gateway-chat"
    assert canonical.system == (TextPart("Be concise."),)
    assert [message.role for message in canonical.messages] == ["user", "assistant", "user", "user"]
    assert canonical.messages[0].content[1] == ImagePart(
        media_type=None,
        url="https://example.test/cat.png",
        detail="high",
    )
    assert canonical.messages[0].content[2] == ImagePart(
        media_type="image/png",
        data="aGVsbG8=",
    )
    assert canonical.messages[1].content[1] == ToolCallPart(
        id="call_weather", name="weather", arguments={"city": "Paris"}
    )
    assert canonical.messages[2].content == (
        ToolResultPart(
            tool_call_id="call_weather",
            name="weather",
            content=(TextPart('{"temperature":21}'),),
        ),
    )
    assert canonical.tool_choice == {"name": "weather"}
    assert canonical.temperature == 0.2
    assert canonical.top_p == 0.9
    assert canonical.max_output_tokens == 128
    assert canonical.stop_sequences == ("END", "STOP")
    assert canonical.stream is True
    assert canonical.metadata["vendor_extensions"]["openai"]["service_tier"] == "auto"


def test_openai_canonical_types_are_frozen(load_fixture) -> None:
    canonical = OpenAIAdapter().decode_request(load_fixture("openai", "request.json"))

    with pytest.raises(FrozenInstanceError):
        canonical.model = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        canonical.metadata["changed"] = True  # type: ignore[index]


def test_openai_golden_response_and_stream(load_fixture, load_bytes) -> None:
    adapter = OpenAIAdapter()
    response = adapter.decode_response(load_fixture("openai", "response.json"))
    events = adapter.decode_stream_event(load_bytes("openai", "stream.sse"))

    assert response.finish_reason == "tool_call"
    assert response.usage is not None
    assert (response.usage.input_tokens, response.usage.output_tokens) == (42, 7)
    assert response.message.content[1] == ToolCallPart(
        id="call_weather", name="weather", arguments={"city": "Paris"}
    )
    content = next(event for event in events if event.type == "content_delta")
    assert content.text == "Hello"
    encoded = adapter.create_stream_encoder().encode(content)
    decoded = tuple(
        item for frame in encoded for item in adapter.create_stream_decoder().decode(frame)
    )
    assert next(event for event in decoded if event.type == "content_delta").text == "Hello"


def test_openai_encode_response_uses_native_finish_reason(load_fixture) -> None:
    adapter = OpenAIAdapter()
    canonical = adapter.decode_response(load_fixture("openai", "response.json"))

    encoded = adapter.encode_response(canonical)

    assert encoded["choices"][0]["finish_reason"] == "tool_calls"
    assert encoded["usage"] == {"prompt_tokens": 42, "completion_tokens": 7, "total_tokens": 49}


@pytest.mark.parametrize(
    ("native", "canonical"),
    [
        ("stop", "stop"),
        ("length", "length"),
        ("tool_calls", "tool_call"),
        ("content_filter", "content_filter"),
    ],
)
def test_openai_finish_reasons(native: str, canonical: str, load_fixture) -> None:
    payload = load_fixture("openai", "response.json")
    payload["choices"][0]["finish_reason"] = native
    assert OpenAIAdapter().decode_response(payload).finish_reason == canonical


def test_same_protocol_passthrough_rewrites_only_selected_upstream_model(load_fixture) -> None:
    raw = orjson.dumps(load_fixture("openai", "request.json"))
    rewritten = rewrite_passthrough_request(Protocol.OPENAI, raw, "provider/model-v2")
    before = orjson.loads(raw)
    after = orjson.loads(rewritten)

    assert after["model"] == "provider/model-v2"
    assert before.pop("model") == "gateway-chat"
    assert after.pop("model") == "provider/model-v2"
    assert after == before


@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_same_protocol_passthrough_forwards_sse_bytes_exactly(protocol, load_bytes) -> None:
    raw = load_bytes(protocol.value, "stream.sse")
    assert rewrite_passthrough_sse(raw) is raw


def test_openai_responses_api_string_input() -> None:
    """Test that Responses API format with string input is converted to messages."""
    adapter = OpenAIAdapter()
    payload = {
        "model": "gpt-4",
        "input": "Hello, how are you?",
    }

    canonical = adapter.decode_request(payload)

    assert canonical.model == "gpt-4"
    assert len(canonical.messages) == 1
    assert canonical.messages[0].role == "user"
    assert canonical.messages[0].content[0].text == "Hello, how are you?"


def test_openai_responses_api_structured_input() -> None:
    """Test that Responses API format with structured input is converted to messages."""
    adapter = OpenAIAdapter()
    payload = {
        "model": "gpt-4",
        "input": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ],
    }

    canonical = adapter.decode_request(payload)

    assert canonical.model == "gpt-4"
    assert len(canonical.messages) == 3
    assert canonical.messages[0].role == "user"
    assert canonical.messages[0].content[0].text == "Hello"
    assert canonical.messages[1].role == "assistant"
    assert canonical.messages[1].content[0].text == "Hi there!"
    assert canonical.messages[2].role == "user"
    assert canonical.messages[2].content[0].text == "How are you?"


def test_openai_responses_api_preserves_other_fields() -> None:
    """Test that Responses API format preserves other fields like temperature, stream, etc."""
    adapter = OpenAIAdapter()
    payload = {
        "model": "gpt-4",
        "input": "Hello",
        "temperature": 0.7,
        "max_tokens": 100,
        "stream": True,
    }

    canonical = adapter.decode_request(payload)

    assert canonical.model == "gpt-4"
    assert canonical.temperature == 0.7
    assert canonical.max_output_tokens == 100
    assert canonical.stream is True


def test_openai_embeddings_api_basic() -> None:
    """Test that embeddings API endpoint exists and can be routed."""
    # This test verifies that the embeddings endpoint is registered
    # The actual embedding generation would be handled by the upstream provider
    from ai_gateway.gateway.openai import router

    # Verify the endpoint is registered
    routes = [route.path for route in router.routes]
    assert "/v1/embeddings" in routes


def test_openai_completions_api_basic() -> None:
    """Test that completions API endpoint exists and can be routed."""
    # This test verifies that the completions endpoint is registered
    # The actual completion generation would be handled by the upstream provider
    from ai_gateway.gateway.openai import router

    # Verify the endpoint is registered
    routes = [route.path for route in router.routes]
    assert "/v1/completions" in routes


def test_openai_responses_api_endpoint_registered() -> None:
    """Test that responses API endpoint exists and can be routed."""
    # This test verifies that the responses endpoint is registered
    from ai_gateway.gateway.openai import router

    # Verify the endpoint is registered
    routes = [route.path for route in router.routes]
    assert "/v1/responses" in routes


def test_responses_api_encode_response() -> None:
    """Test that Responses API response encoding produces correct format."""
    from ai_gateway.protocols.openai import OpenAIAdapter
    from ai_gateway.protocols.types import CanonicalMessage, CanonicalResponse, TextPart, CanonicalUsage

    adapter = OpenAIAdapter()
    response = CanonicalResponse(
        model="gpt-4",
        message=CanonicalMessage(
            role="assistant",
            content=[TextPart("Hello, world!")],
        ),
        finish_reason="stop",
        usage=CanonicalUsage(input_tokens=10, output_tokens=20),
        metadata={},
    )

    encoded = adapter.encode_responses_api_response(response)

    # Verify structure
    assert encoded["object"] == "response"
    assert encoded["id"].startswith("resp_")
    assert encoded["model"] == "gpt-4"
    assert encoded["status"] == "completed"
    assert "output" in encoded
    assert len(encoded["output"]) > 0

    # Verify message item
    message_item = encoded["output"][0]
    assert message_item["type"] == "message"
    assert message_item["role"] == "assistant"
    assert message_item["status"] == "completed"
    assert len(message_item["content"]) > 0
    assert message_item["content"][0]["type"] == "output_text"
    assert message_item["content"][0]["text"] == "Hello, world!"

    # Verify usage
    assert "usage" in encoded
    assert encoded["usage"]["input_tokens"] == 10
    assert encoded["usage"]["output_tokens"] == 20
    assert encoded["usage"]["total_tokens"] == 30


def test_responses_api_encode_response_with_tool_calls() -> None:
    """Test that Responses API response encoding handles tool calls correctly."""
    from ai_gateway.protocols.openai import OpenAIAdapter
    from ai_gateway.protocols.types import (
        CanonicalMessage,
        CanonicalResponse,
        TextPart,
        ToolCallPart,
    )

    adapter = OpenAIAdapter()
    response = CanonicalResponse(
        model="gpt-4",
        message=CanonicalMessage(
            role="assistant",
            content=[
                TextPart("Let me check the weather."),
                ToolCallPart(
                    id="call_123",
                    name="get_weather",
                    arguments={"city": "Paris"},
                ),
            ],
        ),
        finish_reason="tool_call",
        usage=None,
        metadata={},
    )

    encoded = adapter.encode_responses_api_response(response)

    # Should have message item and function_call item
    assert len(encoded["output"]) >= 2
    message_item = encoded["output"][0]
    assert message_item["type"] == "message"

    # Find function_call item
    function_call_item = next(
        (item for item in encoded["output"] if item["type"] == "function_call"),
        None,
    )
    assert function_call_item is not None
    assert function_call_item["name"] == "get_weather"
    assert "Paris" in function_call_item["arguments"]


def test_responses_api_input_types() -> None:
    """Test that Responses API handles various input types correctly."""
    from ai_gateway.protocols.openai import OpenAIAdapter

    adapter = OpenAIAdapter()

    # Test with function_call and function_call_output
    payload = {
        "model": "gpt-4",
        "input": [
            {"type": "message", "role": "user", "content": "What's the weather in Paris?"},
            {
                "type": "function_call",
                "id": "call_123",
                "name": "get_weather",
                "arguments": '{"city": "Paris"}',
            },
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": '{"temperature": 22}',
            },
        ],
    }

    canonical = adapter.decode_request(payload)

    # Should have 3 messages: user, assistant (with tool_call), tool
    assert len(canonical.messages) == 3
    assert canonical.messages[0].role == "user"
    assert canonical.messages[1].role == "assistant"
    assert canonical.messages[2].role == "user"  # Tool results become user messages with ToolResultPart


def test_responses_api_streaming_encoder() -> None:
    """Test that Responses API streaming encoder produces correct events."""
    from ai_gateway.protocols.openai import _ResponsesAPIStreamEncoder
    from ai_gateway.protocols.types import StreamEvent
    from ai_gateway.protocols.base import decode_sse

    encoder = _ResponsesAPIStreamEncoder()

    # Test message_start event
    events = encoder.encode(StreamEvent(type="message_start", role="assistant", model="gpt-4"))
    assert len(events) > 0

    # First event should be response.created
    first_event_type, first_payload = decode_sse(events[0])
    assert first_payload["type"] == "response.created"
    assert first_payload["response"]["id"].startswith("resp_")

    # Test content_delta event
    events = encoder.encode(StreamEvent(type="content_delta", text="Hello"))
    assert len(events) > 0

    # Should have content_part.added and output_text.delta
    event_types = []
    for event_bytes in events:
        _, payload = decode_sse(event_bytes)
        event_types.append(payload["type"])

    assert "response.content_part.added" in event_types
    assert "response.output_text.delta" in event_types

    # Test done event
    events = encoder.encode(StreamEvent(type="done"))
    assert len(events) > 0

    # Should have response.completed
    _, payload = decode_sse(events[-1])
    assert payload["type"] == "response.completed"
