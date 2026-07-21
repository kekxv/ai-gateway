from __future__ import annotations

import orjson

from ai_gateway.protocols.base import decode_sse
from ai_gateway.protocols.registry import get_adapter


def _sse(payload: dict[str, object], event: str | None = None) -> bytes:
    prefix = b"" if event is None else f"event: {event}\n".encode()
    return prefix + b"data: " + orjson.dumps(payload) + b"\n\n"


def test_openai_nested_extensions_round_trip_only_to_openai() -> None:
    payload = {
        "model": "m",
        "messages": [
            {
                "role": "user",
                "name": "alice",
                "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
            }
        ],
        "tools": [
            {
                "type": "function",
                "x-tool": "kept",
                "function": {"name": "f", "parameters": {}, "strict": True},
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "f"},
            "parallel": False,
        },
    }
    request = get_adapter("openai").decode_request(payload)
    same = get_adapter("openai").encode_request(request)

    assert same["messages"][0]["name"] == "alice"
    assert same["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert same["tools"][0]["x-tool"] == "kept"
    assert same["tools"][0]["function"]["strict"] is True
    assert same["tool_choice"]["parallel"] is False
    assert b"cache_control" not in orjson.dumps(get_adapter("claude").encode_request(request))
    assert b"strict" not in orjson.dumps(get_adapter("gemini").encode_request(request))


def test_claude_cache_control_and_nested_extensions_do_not_leak() -> None:
    payload = {
        "model": "m",
        "max_tokens": 8,
        "system": [{"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {
                "role": "user",
                "vendor_message": "kept",
                "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
            }
        ],
        "tools": [{"name": "f", "input_schema": {}, "cache_control": {"type": "ephemeral"}}],
        "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
    }
    request = get_adapter("claude").decode_request(payload)
    same = get_adapter("claude").encode_request(request)

    assert same["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert same["messages"][0]["vendor_message"] == "kept"
    assert same["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert same["tools"][0]["cache_control"] == {"type": "ephemeral"}
    assert same["tool_choice"]["disable_parallel_tool_use"] is True
    assert b"cache_control" not in orjson.dumps(get_adapter("openai").encode_request(request))
    assert b"vendor_message" not in orjson.dumps(get_adapter("gemini").encode_request(request))


def test_gemini_nested_and_generation_extensions_do_not_leak() -> None:
    payload = {
        "model": "m",
        "contents": [
            {
                "role": "user",
                "vendorMessage": "kept",
                "parts": [{"text": "hi", "thoughtSignature": "signature"}],
            }
        ],
        "tools": [
            {
                "vendorGroup": "kept",
                "functionDeclarations": [{"name": "f", "parameters": {}, "behavior": "BLOCKING"}],
            }
        ],
        "toolConfig": {
            "functionCallingConfig": {"mode": "AUTO", "vendorCalling": "kept"},
            "vendorToolConfig": "kept",
        },
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    request = get_adapter("gemini").decode_request(payload)
    same = get_adapter("gemini").encode_request(request)

    assert same["contents"][0]["vendorMessage"] == "kept"
    assert same["contents"][0]["parts"][0]["thoughtSignature"] == "signature"
    assert same["tools"][0]["vendorGroup"] == "kept"
    assert same["tools"][0]["functionDeclarations"][0]["behavior"] == "BLOCKING"
    assert same["toolConfig"]["functionCallingConfig"]["vendorCalling"] == "kept"
    assert same["toolConfig"]["vendorToolConfig"] == "kept"
    assert same["generationConfig"]["responseMimeType"] == "application/json"
    assert b"thoughtSignature" not in orjson.dumps(get_adapter("openai").encode_request(request))
    assert b"responseMimeType" not in orjson.dumps(get_adapter("claude").encode_request(request))


def test_openai_system_developer_and_choice_extensions_round_trip_independently() -> None:
    request_payload = {
        "model": "m",
        "messages": [
            {"role": "system", "content": "one", "name": "system-name"},
            {"role": "developer", "content": "two", "x-developer": True},
            {"role": "user", "content": "hi"},
        ],
    }
    adapter = get_adapter("openai")
    request = adapter.decode_request(request_payload)
    same_request = adapter.encode_request(request)

    assert same_request["messages"][:2] == request_payload["messages"][:2]
    assert b"x-developer" not in orjson.dumps(get_adapter("claude").encode_request(request))

    response_payload = {
        "model": "m",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
                "logprobs": {"content": []},
            }
        ],
    }
    response = adapter.decode_response(response_payload)
    same_response = adapter.encode_response(response)
    assert same_response["choices"][0]["logprobs"] == {"content": []}
    assert b"logprobs" not in orjson.dumps(get_adapter("gemini").encode_response(response))


def test_gemini_candidate_extensions_round_trip_only_to_gemini() -> None:
    payload = {
        "modelVersion": "m",
        "candidates": [
            {
                "index": 0,
                "content": {"role": "model", "parts": [{"text": "ok"}]},
                "finishReason": "STOP",
                "safetyRatings": [{"category": "x", "probability": "LOW"}],
            }
        ],
    }
    adapter = get_adapter("gemini")
    response = adapter.decode_response(payload)
    same = adapter.encode_response(response)

    assert same["candidates"][0]["safetyRatings"] == payload["candidates"][0]["safetyRatings"]
    assert b"safetyRatings" not in orjson.dumps(get_adapter("openai").encode_response(response))


def test_openai_stream_envelope_choice_and_delta_extensions_round_trip() -> None:
    frame = _sse(
        {
            "model": "m",
            "x-envelope": 1,
            "choices": [{"index": 0, "x-choice": 2, "delta": {"content": "hi", "x-delta": 3}}],
        }
    )
    adapter = get_adapter("openai")
    decoder = adapter.create_stream_decoder()
    event = next(item for item in decoder.decode(frame) if item.type == "content_delta")
    encoded = adapter.create_stream_encoder().encode(event)
    body = decode_sse(encoded[0])[1]

    assert body["x-envelope"] == 1
    assert body["choices"][0]["x-choice"] == 2
    assert body["choices"][0]["delta"]["x-delta"] == 3
    assert b"x-envelope" not in b"".join(
        get_adapter("claude").create_stream_encoder().encode(event)
    )


def test_gemini_stream_envelope_candidate_content_and_part_extensions_round_trip() -> None:
    frame = _sse(
        {
            "modelVersion": "m",
            "xEnvelope": 1,
            "candidates": [
                {
                    "index": 0,
                    "xCandidate": 2,
                    "content": {
                        "role": "model",
                        "xContent": 3,
                        "parts": [{"text": "hi", "thoughtSignature": "sig"}],
                    },
                }
            ],
        }
    )
    adapter = get_adapter("gemini")
    event = next(
        item
        for item in adapter.create_stream_decoder().decode(frame)
        if item.type == "content_delta"
    )
    encoded = adapter.create_stream_encoder().encode(event)
    body = decode_sse(encoded[0])[1]

    assert body["xEnvelope"] == 1
    assert body["candidates"][0]["xCandidate"] == 2
    assert body["candidates"][0]["content"]["xContent"] == 3
    assert body["candidates"][0]["content"]["parts"][0]["thoughtSignature"] == "sig"
    assert b"thoughtSignature" not in b"".join(
        get_adapter("openai").create_stream_encoder().encode(event)
    )


def test_claude_stream_envelope_and_delta_extensions_round_trip() -> None:
    frame = _sse(
        {
            "type": "content_block_delta",
            "index": 0,
            "x-envelope": 1,
            "delta": {"type": "text_delta", "text": "hi", "x-delta": 2},
        },
        "content_block_delta",
    )
    adapter = get_adapter("claude")
    event = next(
        item
        for item in adapter.create_stream_decoder().decode(frame)
        if item.type == "content_delta"
    )
    encoded = adapter.create_stream_encoder().encode(event)
    bodies = tuple(decode_sse(item)[1] for item in encoded)
    delta = next(body for body in bodies if body["type"] == "content_block_delta")

    assert delta["x-envelope"] == 1
    assert delta["delta"]["x-delta"] == 2
    assert b"x-envelope" not in b"".join(
        get_adapter("gemini").create_stream_encoder().encode(event)
    )
