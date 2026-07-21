from __future__ import annotations

from collections.abc import Iterable

import orjson

from ai_gateway.protocols.base import decode_sse
from ai_gateway.protocols.registry import get_adapter


def _sse(payload: dict[str, object], event: str | None = None) -> bytes:
    prefix = b"" if event is None else f"event: {event}\n".encode()
    return prefix + b"data: " + orjson.dumps(payload) + b"\n\n"


def _native_bodies(frames: Iterable[bytes]) -> tuple[dict[str, object], ...]:
    return tuple(decode_sse(frame)[1] for frame in frames)


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


def test_openai_stream_tool_item_and_function_extensions_round_trip() -> None:
    frame = _sse(
        {
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "a",
                                "type": "function",
                                "x-tool": 1,
                                "function": {
                                    "name": "one",
                                    "arguments": "{}",
                                    "x-function": 2,
                                },
                            }
                        ]
                    },
                }
            ],
        }
    )
    adapter = get_adapter("openai")
    event = next(
        item
        for item in adapter.create_stream_decoder().decode(frame)
        if item.type == "tool_call_delta"
    )
    body = decode_sse(adapter.create_stream_encoder().encode(event)[0])[1]
    tool = body["choices"][0]["delta"]["tool_calls"][0]

    assert tool["x-tool"] == 1
    assert tool["function"]["x-function"] == 2
    assert b"x-function" not in b"".join(
        get_adapter("gemini").create_stream_encoder().encode(event)
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


def test_claude_stream_message_start_and_message_extensions_round_trip() -> None:
    frame = _sse(
        {
            "type": "message_start",
            "x-envelope": 1,
            "message": {
                "type": "message",
                "role": "assistant",
                "model": "m",
                "content": [],
                "usage": {"input_tokens": 3},
                "x-message": 2,
            },
        },
        "message_start",
    )
    adapter = get_adapter("claude")
    event = adapter.create_stream_decoder().decode(frame)[0]
    body = decode_sse(adapter.create_stream_encoder().encode(event)[0])[1]

    assert body["x-envelope"] == 1
    assert body["message"]["x-message"] == 2
    assert b"x-envelope" not in b"".join(
        get_adapter("openai").create_stream_encoder().encode(event)
    )


def test_claude_stream_content_start_block_and_stop_extensions_round_trip() -> None:
    adapter = get_adapter("claude")
    decoder = adapter.create_stream_decoder()
    events = (
        *decoder.decode(
            _sse(
                {
                    "type": "content_block_start",
                    "index": 4,
                    "x-start": 1,
                    "content_block": {"type": "text", "text": "", "x-block": 2},
                },
                "content_block_start",
            )
        ),
        *decoder.decode(
            _sse(
                {"type": "content_block_stop", "index": 4, "x-stop": 3},
                "content_block_stop",
            )
        ),
    )
    encoder = adapter.create_stream_encoder()
    encoded = _native_bodies(frame for event in events for frame in encoder.encode(event))

    start = next(body for body in encoded if body["type"] == "content_block_start")
    stop = next(body for body in encoded if body["type"] == "content_block_stop")
    assert start["x-start"] == 1
    assert start["content_block"]["x-block"] == 2
    assert stop["x-stop"] == 3


def test_claude_stream_message_delta_and_stop_extensions_round_trip() -> None:
    adapter = get_adapter("claude")
    decoder = adapter.create_stream_decoder()
    canonical = (
        *decoder.decode(
            _sse(
                {
                    "type": "message_start",
                    "message": {"role": "assistant", "model": "m", "usage": {"input_tokens": 3}},
                },
                "message_start",
            )
        ),
        *decoder.decode(
            _sse(
                {
                    "type": "message_delta",
                    "x-delta-envelope": 1,
                    "delta": {"stop_reason": "end_turn", "x-message-delta": 2},
                    "usage": {"output_tokens": 4},
                },
                "message_delta",
            )
        ),
        *decoder.decode(_sse({"type": "message_stop", "x-message-stop": 3}, "message_stop")),
    )
    encoder = adapter.create_stream_encoder()
    encoded = _native_bodies(frame for event in canonical for frame in encoder.encode(event))

    delta = next(body for body in encoded if body["type"] == "message_delta")
    stop = next(body for body in encoded if body["type"] == "message_stop")
    assert delta["x-delta-envelope"] == 1
    assert delta["delta"]["x-message-delta"] == 2
    assert stop["x-message-stop"] == 3
    openai_encoder = get_adapter("openai").create_stream_encoder()
    cross = b"".join(frame for event in canonical for frame in openai_encoder.encode(event))
    assert b"x-delta-envelope" not in cross
    assert b"x-message-stop" not in cross


def test_claude_stream_ping_and_error_extensions_round_trip() -> None:
    adapter = get_adapter("claude")
    ping = adapter.create_stream_decoder().decode(_sse({"type": "ping", "x-ping": 1}, "ping"))[0]
    error = adapter.create_stream_decoder().decode(
        _sse(
            {
                "type": "error",
                "x-error-envelope": 2,
                "error": {"type": "overloaded_error", "message": "bad", "x-error": 3},
            },
            "error",
        )
    )[0]

    ping_body = decode_sse(adapter.create_stream_encoder().encode(ping)[0])[1]
    error_body = decode_sse(adapter.create_stream_encoder().encode(error)[0])[1]
    assert ping_body["x-ping"] == 1
    assert error_body["x-error-envelope"] == 2
    assert error_body["error"]["x-error"] == 3
    cross_error = b"".join(get_adapter("openai").create_stream_encoder().encode(error))
    assert b"x-error-envelope" not in cross_error
    assert b"x-error" not in cross_error
