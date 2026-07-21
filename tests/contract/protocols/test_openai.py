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
