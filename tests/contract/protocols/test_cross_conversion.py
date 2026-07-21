from __future__ import annotations

from dataclasses import replace

import orjson
import pytest

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import rewrite_passthrough_request
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import CanonicalRequest, CanonicalResponse, StreamEvent

PROTOCOLS = tuple(Protocol)


def semantic_request(request: CanonicalRequest) -> CanonicalRequest:
    return replace(request, metadata={})


def semantic_response(response: CanonicalResponse) -> CanonicalResponse:
    return replace(response, metadata={})


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

    assert semantic_request(decoded) == semantic_request(canonical)
    if source != target:
        assert "service_tier" not in converted
        assert "cachedContent" not in converted


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

    assert semantic_response(decoded) == semantic_response(canonical)


@pytest.mark.parametrize("source", PROTOCOLS)
@pytest.mark.parametrize("target", PROTOCOLS)
def test_all_nine_sse_conversion_pairs_preserve_delta_semantics(source, target, load_bytes) -> None:
    source_adapter = get_adapter(source)
    target_adapter = get_adapter(target)
    canonical = source_adapter.decode_stream_event(load_bytes(source.value, "stream.sse"))

    converted = target_adapter.encode_stream_event(canonical)
    decoded = target_adapter.decode_stream_event(converted)

    assert semantic_stream_event(decoded) == semantic_stream_event(canonical)


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
