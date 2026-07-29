from __future__ import annotations

from dataclasses import replace

import orjson
import pytest

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import rewrite_passthrough_request
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import (
    CanonicalMessage,
    CanonicalRequest,
    CanonicalResponse,
    CanonicalTool,
    CanonicalUsage,
    ContentPart,
    ImagePart,
    StreamEvent,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)

PROTOCOLS = tuple(Protocol)


def expected_request() -> CanonicalRequest:
    return CanonicalRequest(
        model="gateway-chat",
        messages=(
            CanonicalMessage(
                "user",
                (
                    TextPart("Inspect both images."),
                    ImagePart(media_type="image/png", url="https://example.test/cat.png"),
                    ImagePart(media_type="image/png", data="aGVsbG8="),
                ),
            ),
            CanonicalMessage(
                "assistant",
                (
                    TextPart("I will check the weather."),
                    ToolCallPart("call_weather", "weather", {"city": "Paris"}),
                ),
            ),
            CanonicalMessage(
                "user",
                (
                    ToolResultPart(
                        "call_weather",
                        "weather",
                        (TextPart('{"temperature":21}'),),
                    ),
                ),
            ),
            CanonicalMessage("user", (TextPart("Summarize it."),)),
        ),
        system=(TextPart("Be concise."),),
        tools=(
            CanonicalTool(
                "weather",
                "Get weather",
                {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            ),
        ),
        tool_choice={"name": "weather"},
        temperature=0.2,
        top_p=0.9,
        max_output_tokens=128,
        stop_sequences=("END", "STOP"),
        stream=True,
        metadata={},
    )


def expected_response(model: str) -> CanonicalResponse:
    return CanonicalResponse(
        model=model,
        message=CanonicalMessage(
            "assistant",
            (
                TextPart("Calling weather."),
                ToolCallPart("call_weather", "weather", {"city": "Paris"}),
            ),
        ),
        finish_reason="tool_call",
        usage=CanonicalUsage(42, 7),
        metadata={},
    )


def semantic_part(part: ContentPart) -> ContentPart:
    if isinstance(part, ToolResultPart):
        return replace(
            part,
            content=tuple(semantic_part(item) for item in part.content),
            metadata={},
        )
    return replace(part, metadata={})


def semantic_message(message: CanonicalMessage) -> CanonicalMessage:
    return replace(
        message,
        content=tuple(semantic_part(part) for part in message.content),
        metadata={},
    )


def semantic_tool(tool: CanonicalTool) -> CanonicalTool:
    return replace(tool, metadata={})


def semantic_request(request: CanonicalRequest) -> CanonicalRequest:
    return replace(
        request,
        messages=tuple(semantic_message(message) for message in request.messages),
        system=tuple(semantic_part(part) for part in request.system),
        tools=tuple(semantic_tool(tool) for tool in request.tools),
        metadata={},
    )


def semantic_response(response: CanonicalResponse) -> CanonicalResponse:
    return replace(response, message=semantic_message(response.message), metadata={})


def semantic_stream_event(event: StreamEvent) -> StreamEvent:
    # Claude content deltas have no model envelope, so model is an unavoidable stream-only loss.
    return replace(event, model=None, metadata={})


@pytest.mark.parametrize("source", PROTOCOLS)
@pytest.mark.parametrize("target", PROTOCOLS)
def test_all_nine_request_conversion_pairs_preserve_semantics(source, target, load_fixture) -> None:
    source_adapter = get_adapter(source)
    target_adapter = get_adapter(target)
    canonical = source_adapter.decode_request(load_fixture(source.value, "request.json"))

    converted = target_adapter.encode_request(canonical)
    decoded = target_adapter.decode_request(converted)

    assert semantic_request(canonical) == expected_request()
    assert semantic_request(decoded) == expected_request()
    if source != target:
        assert "service_tier" not in converted
        assert "cachedContent" not in converted


@pytest.mark.parametrize("target", (Protocol.OPENAI, Protocol.GEMINI))
def test_claude_system_message_converts_to_target_system_instruction(target: Protocol) -> None:
    canonical = get_adapter(Protocol.CLAUDE).decode_request(
        {
            "model": "claude-model",
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "Follow system policy."}],
                },
                {"role": "user", "content": "Hello"},
            ],
            "max_tokens": 128,
        }
    )

    converted = get_adapter(target).encode_request(canonical)

    if target is Protocol.OPENAI:
        assert converted["messages"][0] == {
            "role": "system",
            "content": "Follow system policy.",
        }
    else:
        assert converted["systemInstruction"] == {"parts": [{"text": "Follow system policy."}]}


@pytest.mark.parametrize("source", PROTOCOLS)
@pytest.mark.parametrize("target", PROTOCOLS)
def test_all_nine_response_conversion_pairs_preserve_semantics(
    source, target, load_fixture
) -> None:
    source_adapter = get_adapter(source)
    target_adapter = get_adapter(target)
    canonical = source_adapter.decode_response(load_fixture(source.value, "response.json"))

    converted = target_adapter.encode_response(canonical)
    decoded = target_adapter.decode_response(converted)

    expected = expected_response(canonical.model)
    assert semantic_response(canonical) == expected
    assert semantic_response(decoded) == expected


@pytest.mark.parametrize("source", PROTOCOLS)
@pytest.mark.parametrize("target", PROTOCOLS)
def test_all_nine_sse_conversion_pairs_preserve_delta_semantics(source, target, load_bytes) -> None:
    source_adapter = get_adapter(source)
    target_adapter = get_adapter(target)
    canonical = source_adapter.create_stream_decoder().decode(
        load_bytes(source.value, "stream.sse")
    )

    encoder = target_adapter.create_stream_encoder()
    converted = tuple(frame for event in canonical for frame in encoder.encode(event))
    decoder = target_adapter.create_stream_decoder()
    decoded = tuple(
        decoded_event for frame in converted if frame for decoded_event in decoder.decode(frame)
    )

    assert [event.text for event in canonical if event.type == "content_delta"] == ["Hello"]
    assert [event.text for event in decoded if event.type == "content_delta"] == ["Hello"]


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_passthrough_always_uses_selected_route_model(protocol, load_fixture) -> None:
    payload = load_fixture(protocol.value, "request.json")
    payload["model"] = "requested-alias"

    rewritten = rewrite_passthrough_request(protocol, orjson.dumps(payload), "selected-upstream")
    rewritten_payload = orjson.loads(rewritten)

    assert rewritten_payload.pop("model") == "selected-upstream"
    payload.pop("model")
    assert rewritten_payload == payload


def test_registry_accepts_protocol_strings() -> None:
    assert get_adapter("openai").protocol is Protocol.OPENAI
    assert get_adapter("claude").protocol is Protocol.CLAUDE
    assert get_adapter("gemini").protocol is Protocol.GEMINI
