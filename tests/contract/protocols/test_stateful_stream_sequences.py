from __future__ import annotations

from collections.abc import Iterable

import orjson
import pytest

from ai_gateway.protocols.base import decode_sse
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import CanonicalUsage, StreamEvent


def _sse(payload: dict[str, object], event: str | None = None) -> bytes:
    prefix = b"" if event is None else f"event: {event}\n".encode()
    return prefix + b"data: " + orjson.dumps(payload) + b"\n\n"


def _decode_sequence(protocol: str, frames: Iterable[bytes]) -> tuple[StreamEvent, ...]:
    decoder = get_adapter(protocol).create_stream_decoder()
    return tuple(event for frame in frames for event in decoder.decode(frame))


def _encode_sequence(protocol: str, events: Iterable[StreamEvent]) -> tuple[bytes, ...]:
    event_sequence = tuple(events)
    encoder = get_adapter(protocol).create_stream_encoder()
    if protocol == "claude":
        final_usage = next(
            (
                event.usage
                for event in reversed(event_sequence)
                if event.type == "usage" and event.usage is not None
            ),
            None,
        )
        if final_usage is not None:
            encoder.set_initial_usage(final_usage.input_tokens)
    return tuple(frame for event in event_sequence for frame in encoder.encode(event) if frame)


def _native_bodies(frames: Iterable[bytes]) -> tuple[dict[str, object], ...]:
    return tuple(decode_sse(frame)[1] for frame in frames)


def _fixture_frames(data: bytes) -> tuple[bytes, ...]:
    return tuple(chunk + b"\n\n" for chunk in data.strip().split(b"\n\n"))


def test_openai_decoder_tracks_boundaries_and_parallel_native_tool_indices() -> None:
    frames = (
        _sse(
            {
                "model": "m",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
        ),
        _sse(
            {
                "model": "m",
                "choices": [{"index": 0, "delta": {"content": "Hel"}, "finish_reason": None}],
            }
        ),
        _sse(
            {
                "model": "m",
                "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": None}],
            }
        ),
        _sse(
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
                                    "function": {"name": "one", "arguments": '{"x":'},
                                },
                                {
                                    "index": 1,
                                    "id": "b",
                                    "type": "function",
                                    "function": {"name": "two", "arguments": '{"y":'},
                                },
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        ),
        _sse(
            {
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": "1}"}},
                                {"index": 1, "function": {"arguments": "2}"}},
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
        ),
        _sse(
            {
                "model": "m",
                "choices": [],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            }
        ),
        b"data: [DONE]\n\n",
    )

    events = _decode_sequence("openai", frames)

    assert [event.type for event in events] == [
        "message_start",
        "content_start",
        "content_delta",
        "content_delta",
        "content_end",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_delta",
        "content_end",
        "content_end",
        "message_end",
        "usage",
        "done",
    ]
    tool_events = [event for event in events if event.type == "tool_call_delta"]
    assert [(event.tool_index, event.tool_call_id, event.tool_name) for event in tool_events] == [
        (0, "a", "one"),
        (1, "b", "two"),
        (0, None, None),
        (1, None, None),
    ]
    assert events[-3].finish_reason == "tool_call"
    assert events[-2].usage == CanonicalUsage(3, 4)


def test_claude_decoder_does_not_invent_empty_tool_arguments() -> None:
    events = _decode_sequence(
        "claude",
        (
            _sse(
                {
                    "type": "content_block_start",
                    "index": 3,
                    "content_block": {"type": "tool_use", "id": "a", "name": "one", "input": {}},
                },
                "content_block_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 3,
                    "delta": {"type": "input_json_delta", "partial_json": '{"x":1}'},
                },
                "content_block_delta",
            ),
            _sse({"type": "content_block_stop", "index": 3}, "content_block_stop"),
        ),
    )

    assert events == (
        StreamEvent(
            type="tool_call_delta",
            index=3,
            tool_index=0,
            content_type="tool_call",
            tool_call_id="a",
            tool_name="one",
        ),
        StreamEvent(
            type="tool_call_delta",
            index=3,
            tool_index=0,
            content_type="tool_call",
            arguments_delta='{"x":1}',
        ),
        StreamEvent(type="content_end", index=3, content_type="tool_call", tool_index=0),
    )


def test_claude_encoder_synthesizes_balanced_blocks_and_accepts_partial_tool_json() -> None:
    events = (
        StreamEvent(type="message_start", role="assistant", model="m"),
        StreamEvent(type="content_delta", index=0, text="Hel"),
        StreamEvent(type="content_delta", index=0, text="lo"),
        StreamEvent(
            type="tool_call_delta", index=1, tool_index=0, tool_call_id="a", tool_name="one"
        ),
        StreamEvent(type="tool_call_delta", index=1, tool_index=0, arguments_delta='{"x":'),
        StreamEvent(type="tool_call_delta", index=1, tool_index=0, arguments_delta="1}"),
        StreamEvent(type="message_end", finish_reason="tool_call"),
        StreamEvent(type="done"),
    )

    bodies = _native_bodies(_encode_sequence("claude", events))

    assert [body["type"] for body in bodies] == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    assert bodies[1]["index"] == 0
    assert bodies[5]["index"] == 1
    assert bodies[5]["content_block"]["input"] == {}
    assert bodies[6]["delta"]["partial_json"] == '{"x":'
    assert bodies[7]["delta"]["partial_json"] == "1}"


def test_claude_usage_is_one_final_cumulative_total_for_cross_protocol_targets(
    load_bytes,
) -> None:
    frames = _fixture_frames(load_bytes("claude", "stream_usage.sse"))
    canonical = _decode_sequence("claude", frames)

    usage_events = [event for event in canonical if event.type == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0].usage == CanonicalUsage(11, 7)
    start = next(event for event in canonical if event.type == "message_start")
    assert start.usage == CanonicalUsage(11, 0)

    openai = _native_bodies(_encode_sequence("openai", canonical))
    openai_usage = [
        body["usage"] for body in openai if isinstance(body, dict) and body.get("usage")
    ]
    assert openai_usage == [{"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}]

    gemini = _native_bodies(_encode_sequence("gemini", canonical))
    gemini_usage = [body["usageMetadata"] for body in gemini if body.get("usageMetadata")]
    assert gemini_usage == [
        {"promptTokenCount": 11, "candidatesTokenCount": 7, "totalTokenCount": 18}
    ]


def test_claude_same_protocol_usage_returns_to_native_start_and_final_delta(load_bytes) -> None:
    native = _fixture_frames(load_bytes("claude", "stream_usage.sse"))
    canonical = _decode_sequence("claude", native)
    encoded = _native_bodies(_encode_sequence("claude", canonical))

    assert [body["type"] for body in encoded] == [
        "message_start",
        "message_delta",
        "message_stop",
    ]
    assert encoded[0]["message"]["usage"] == {"input_tokens": 11}
    assert encoded[1]["delta"]["stop_reason"] == "end_turn"
    assert encoded[1]["usage"] == {"output_tokens": 7}


def test_claude_encoder_accepts_initial_usage_hook_before_message_start() -> None:
    encoder = get_adapter("claude").create_stream_encoder()
    encoder.set_initial_usage(5)

    frames = encoder.encode(StreamEvent(type="message_start", role="assistant", model="m"))
    body = decode_sse(frames[0])[1]

    assert body["message"]["usage"] == {"input_tokens": 5}


def test_gemini_stop_after_prior_function_call_is_statefully_tool_call() -> None:
    frames = (
        _sse(
            {
                "modelVersion": "m",
                "candidates": [
                    {
                        "index": 0,
                        "content": {
                            "role": "model",
                            "parts": [
                                {"functionCall": {"id": "a", "name": "one", "args": {"x": 1}}},
                                {"functionCall": {"id": "b", "name": "two", "args": {"y": 2}}},
                            ],
                        },
                    }
                ],
            }
        ),
        _sse({"modelVersion": "m", "candidates": [{"index": 0, "finishReason": "STOP"}]}),
        b"",
    )

    events = _decode_sequence("gemini", frames)
    tool_events = [event for event in events if event.type == "tool_call_delta"]

    assert [(event.index, event.tool_index, event.tool_call_id) for event in tool_events] == [
        (0, 0, "a"),
        (1, 1, "b"),
    ]
    assert [event.type for event in events[-4:]] == [
        "content_end",
        "content_end",
        "message_end",
        "done",
    ]
    assert events[-2].finish_reason == "tool_call"


def test_gemini_encoder_buffers_partial_arguments_until_tool_end_and_round_trips_finish() -> None:
    canonical = (
        StreamEvent(type="message_start", role="assistant", model="m"),
        StreamEvent(
            type="tool_call_delta", index=0, tool_index=0, tool_call_id="a", tool_name="one"
        ),
        StreamEvent(type="tool_call_delta", index=0, tool_index=0, arguments_delta='{"x":'),
        StreamEvent(type="tool_call_delta", index=0, tool_index=0, arguments_delta="1}"),
        StreamEvent(type="content_end", index=0, content_type="tool_call", tool_index=0),
        StreamEvent(type="message_end", finish_reason="tool_call", model="m"),
        StreamEvent(type="done"),
    )

    frames = _encode_sequence("gemini", canonical)
    bodies = _native_bodies(frames)
    decoded = _decode_sequence("gemini", (*frames, b""))

    assert bodies[0]["candidates"][0]["content"]["parts"] == [
        {"functionCall": {"name": "one", "args": {"x": 1}, "id": "a"}}
    ]
    assert bodies[1]["candidates"][0]["finishReason"] == "STOP"
    assert (
        next(event for event in decoded if event.type == "message_end").finish_reason == "tool_call"
    )


@pytest.mark.parametrize("source", ("openai", "claude", "gemini"))
@pytest.mark.parametrize("target", ("openai", "claude", "gemini"))
def test_all_nine_pairs_convert_a_complete_incremental_sequence(source: str, target: str) -> None:
    source_frames = {
        "openai": (
            _sse({"model": "m", "choices": [{"index": 0, "delta": {"role": "assistant"}}]}),
            _sse({"model": "m", "choices": [{"index": 0, "delta": {"content": "H"}}]}),
            _sse({"model": "m", "choices": [{"index": 0, "delta": {"content": "i"}}]}),
            _sse(
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
                                        "function": {"name": "one", "arguments": '{"x":1}'},
                                    },
                                    {
                                        "index": 1,
                                        "id": "b",
                                        "type": "function",
                                        "function": {"name": "two", "arguments": '{"y":2}'},
                                    },
                                ]
                            },
                        }
                    ],
                }
            ),
            _sse(
                {
                    "model": "m",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                }
            ),
            _sse(
                {"model": "m", "choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}
            ),
            b"data: [DONE]\n\n",
        ),
        "claude": (
            _sse(
                {
                    "type": "message_start",
                    "message": {
                        "role": "assistant",
                        "model": "m",
                        "usage": {"input_tokens": 2},
                    },
                },
                "message_start",
            ),
            _sse(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
                "content_block_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "H"},
                },
                "content_block_delta",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "i"},
                },
                "content_block_delta",
            ),
            _sse({"type": "content_block_stop", "index": 0}, "content_block_stop"),
            _sse(
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {"type": "tool_use", "id": "a", "name": "one", "input": {}},
                },
                "content_block_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "input_json_delta", "partial_json": '{"x":1}'},
                },
                "content_block_delta",
            ),
            _sse({"type": "content_block_stop", "index": 1}, "content_block_stop"),
            _sse(
                {
                    "type": "content_block_start",
                    "index": 2,
                    "content_block": {"type": "tool_use", "id": "b", "name": "two", "input": {}},
                },
                "content_block_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 2,
                    "delta": {"type": "input_json_delta", "partial_json": '{"y":2}'},
                },
                "content_block_delta",
            ),
            _sse({"type": "content_block_stop", "index": 2}, "content_block_stop"),
            _sse(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use"},
                    "usage": {"output_tokens": 3},
                },
                "message_delta",
            ),
            _sse({"type": "message_stop"}, "message_stop"),
        ),
        "gemini": (
            _sse(
                {
                    "modelVersion": "m",
                    "candidates": [
                        {"index": 0, "content": {"role": "model", "parts": [{"text": "H"}]}}
                    ],
                }
            ),
            _sse(
                {
                    "modelVersion": "m",
                    "candidates": [
                        {"index": 0, "content": {"role": "model", "parts": [{"text": "i"}]}}
                    ],
                }
            ),
            _sse(
                {
                    "modelVersion": "m",
                    "candidates": [
                        {
                            "index": 0,
                            "content": {
                                "role": "model",
                                "parts": [
                                    {"functionCall": {"id": "a", "name": "one", "args": {"x": 1}}},
                                    {"functionCall": {"id": "b", "name": "two", "args": {"y": 2}}},
                                ],
                            },
                        }
                    ],
                }
            ),
            _sse(
                {
                    "modelVersion": "m",
                    "candidates": [{"index": 0, "finishReason": "STOP"}],
                    "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3},
                }
            ),
            b"",
        ),
    }[source]

    canonical = _decode_sequence(source, source_frames)
    target_frames = _encode_sequence(target, canonical)
    target_events = _decode_sequence(
        target, (*target_frames, *((b"",) if target == "gemini" else ()))
    )

    assert "content_start" in [event.type for event in target_events]
    assert [event.text for event in target_events if event.type == "content_delta"] == ["H", "i"]
    assert [
        (event.tool_call_id, event.tool_name)
        for event in target_events
        if event.type == "tool_call_delta" and event.tool_call_id is not None
    ] == [("a", "one"), ("b", "two")]
    assert (
        next(event for event in target_events if event.type == "message_end").finish_reason
        == "tool_call"
    )
    assert next(event for event in target_events if event.type == "usage").usage == CanonicalUsage(
        2, 3
    )
    if target == "claude":
        native_types = [decode_sse(frame)[1]["type"] for frame in target_frames]
        assert native_types.index("content_block_start") < native_types.index("content_block_delta")
        assert native_types.index("content_block_stop") < native_types.index("message_delta")
        start_indices = [
            body["index"]
            for body in _native_bodies(target_frames)
            if body["type"] == "content_block_start"
        ]
        assert start_indices == [0, 1, 2]
    elif target == "openai":
        tool_indices = [
            body["choices"][0]["delta"]["tool_calls"][0]["index"]
            for body in _native_bodies(target_frames)
            if isinstance(body, dict)
            and body.get("choices")
            and body["choices"][0].get("delta", {}).get("tool_calls")
            and body["choices"][0]["delta"]["tool_calls"][0].get("id")
        ]
        assert tool_indices == [0, 1]
    else:
        calls = [
            part["functionCall"]["name"]
            for body in _native_bodies(target_frames)
            for candidate in body.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
            if "functionCall" in part
        ]
        assert calls == ["one", "two"]


@pytest.mark.parametrize("source", ("openai", "claude", "gemini"))
@pytest.mark.parametrize("target", ("openai", "claude", "gemini"))
def test_all_nine_pairs_preserve_normal_finish_and_terminal(source: str, target: str) -> None:
    normal_frames = {
        "openai": (
            _sse({"model": "m", "choices": [{"index": 0, "delta": {"content": "ok"}}]}),
            _sse({"model": "m", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
            b"data: [DONE]\n\n",
        ),
        "claude": (
            _sse(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
                "content_block_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "ok"},
                },
                "content_block_delta",
            ),
            _sse({"type": "content_block_stop", "index": 0}, "content_block_stop"),
            _sse({"type": "message_delta", "delta": {"stop_reason": "end_turn"}}, "message_delta"),
            _sse({"type": "message_stop"}, "message_stop"),
        ),
        "gemini": (
            _sse(
                {
                    "modelVersion": "m",
                    "candidates": [
                        {"index": 0, "content": {"role": "model", "parts": [{"text": "ok"}]}}
                    ],
                }
            ),
            _sse({"modelVersion": "m", "candidates": [{"index": 0, "finishReason": "STOP"}]}),
            b"",
        ),
    }[source]
    canonical = _decode_sequence(source, normal_frames)
    target_frames = _encode_sequence(target, canonical)
    decoded = _decode_sequence(target, (*target_frames, *((b"",) if target == "gemini" else ())))

    assert next(event for event in decoded if event.type == "message_end").finish_reason == "stop"
    assert any(event.type == "done" for event in decoded)


@pytest.mark.parametrize("source", ("openai", "claude", "gemini"))
@pytest.mark.parametrize("target", ("openai", "claude", "gemini"))
def test_all_nine_pairs_preserve_stream_errors(source: str, target: str) -> None:
    error_frames = {
        "openai": (_sse({"error": {"message": "bad", "code": "x"}}),),
        "claude": (_sse({"type": "error", "error": {"message": "bad", "code": "x"}}, "error"),),
        "gemini": (_sse({"error": {"message": "bad", "code": "x"}}),),
    }[source]
    canonical = _decode_sequence(source, error_frames)
    target_frames = _encode_sequence(target, canonical)
    decoded = _decode_sequence(target, target_frames)

    error = next(event for event in decoded if event.type == "error")
    assert error.metadata["message"] == "bad"
    assert error.metadata["code"] == "x"
