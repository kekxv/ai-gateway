from __future__ import annotations

import orjson

from ai_gateway.protocols.base import decode_sse
from ai_gateway.protocols.claude import ClaudeAdapter
from ai_gateway.protocols.gemini import GeminiAdapter
from ai_gateway.protocols.openai import OpenAIAdapter
from ai_gateway.protocols.types import CanonicalUsage, StreamEvent


def _sse(payload: dict[str, object], event: str | None = None) -> bytes:
    prefix = b"" if event is None else f"event: {event}\n".encode()
    return prefix + b"data: " + orjson.dumps(payload) + b"\n\n"


def test_openai_combined_chunk_emits_every_event_in_order() -> None:
    frame = _sse(
        {
            "model": "model-a",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": "Hi",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "weather", "arguments": '{"city":'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4},
        }
    )

    assert OpenAIAdapter().decode_stream_event(frame) == (
        StreamEvent(type="message_start", role="assistant", model="model-a"),
        StreamEvent(type="content_delta", text="Hi", model="model-a"),
        StreamEvent(
            type="tool_call_delta",
            tool_call_id="call_1",
            tool_name="weather",
            arguments_delta='{"city":',
            model="model-a",
        ),
        StreamEvent(type="message_end", finish_reason="tool_call", model="model-a"),
        StreamEvent(type="usage", usage=CanonicalUsage(3, 4), model="model-a"),
    )


def test_openai_error_and_done_are_distinct_terminal_events() -> None:
    adapter = OpenAIAdapter()

    assert adapter.decode_stream_event(_sse({"error": {"message": "bad", "code": "x"}})) == (
        StreamEvent(type="error", metadata={"message": "bad", "code": "x"}),
    )
    assert adapter.decode_stream_event(b"data: [DONE]\n\n") == (StreamEvent(type="done"),)
    assert adapter.encode_stream_event(StreamEvent(type="done")) == b"data: [DONE]\n\n"


def test_openai_encodes_each_canonical_event_to_the_expected_native_shape() -> None:
    adapter = OpenAIAdapter()
    events = (
        StreamEvent(type="message_start", role="assistant", model="m"),
        StreamEvent(type="content_delta", text="Hi", model="m"),
        StreamEvent(
            type="tool_call_delta",
            tool_call_id="c",
            tool_name="f",
            arguments_delta="{}",
            model="m",
        ),
        StreamEvent(type="message_end", finish_reason="tool_call", model="m"),
        StreamEvent(type="usage", usage=CanonicalUsage(2, 3), model="m"),
        StreamEvent(type="error", metadata={"message": "bad"}),
    )

    bodies = tuple(decode_sse(adapter.encode_stream_event(event))[1] for event in events)

    assert bodies[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert bodies[1]["choices"][0]["delta"] == {"content": "Hi"}
    assert bodies[2]["choices"][0]["delta"]["tool_calls"][0]["function"] == {
        "name": "f",
        "arguments": "{}",
    }
    assert bodies[3]["choices"][0]["finish_reason"] == "tool_calls"
    assert bodies[4]["choices"] == []
    assert bodies[4]["usage"]["completion_tokens"] == 3
    assert bodies[5] == {"error": {"message": "bad"}}


def test_claude_all_native_event_shapes_have_independent_canonical_sequences() -> None:
    adapter = ClaudeAdapter()

    assert adapter.decode_stream_event(
        _sse(
            {
                "type": "message_start",
                "message": {"role": "assistant", "model": "claude-x", "usage": {"input_tokens": 3}},
            },
            "message_start",
        )
    ) == (
        StreamEvent(type="message_start", role="assistant", model="claude-x"),
        StreamEvent(type="usage", usage=CanonicalUsage(3, 0), model="claude-x"),
    )
    assert adapter.decode_stream_event(
        _sse(
            {
                "type": "content_block_start",
                "index": 2,
                "content_block": {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "weather",
                    "input": {"city": "Paris"},
                },
            },
            "content_block_start",
        )
    ) == (
        StreamEvent(
            type="tool_call_delta",
            index=2,
            tool_call_id="call_1",
            tool_name="weather",
            arguments_delta='{"city":"Paris"}',
        ),
    )
    assert adapter.decode_stream_event(
        _sse(
            {
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "input_json_delta", "partial_json": "}"},
            },
            "content_block_delta",
        )
    ) == (StreamEvent(type="tool_call_delta", index=2, arguments_delta="}"),)
    assert adapter.decode_stream_event(
        _sse({"type": "content_block_stop", "index": 2}, "content_block_stop")
    ) == (StreamEvent(type="content_end", index=2),)
    assert adapter.decode_stream_event(
        _sse(
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 4},
            },
            "message_delta",
        )
    ) == (
        StreamEvent(type="message_end", finish_reason="stop"),
        StreamEvent(type="usage", usage=CanonicalUsage(0, 4)),
    )
    assert adapter.decode_stream_event(
        _sse(
            {"type": "message_delta", "delta": {}, "usage": {"output_tokens": 4}},
            "message_delta",
        )
    ) == (StreamEvent(type="usage", usage=CanonicalUsage(0, 4)),)
    assert adapter.decode_stream_event(_sse({"type": "message_stop"}, "message_stop")) == (
        StreamEvent(type="done"),
    )
    assert adapter.decode_stream_event(_sse({"type": "ping"}, "ping")) == (
        StreamEvent(type="heartbeat"),
    )
    assert adapter.decode_stream_event(
        _sse({"type": "error", "error": {"type": "overloaded_error"}}, "error")
    ) == (StreamEvent(type="error", metadata={"type": "overloaded_error"}),)


def test_claude_encoded_native_shapes_decode_without_invented_finish() -> None:
    adapter = ClaudeAdapter()
    events = (
        StreamEvent(type="content_end", index=3),
        StreamEvent(type="usage", usage=CanonicalUsage(0, 5)),
        StreamEvent(type="heartbeat"),
        StreamEvent(type="done"),
    )

    encoded = tuple(adapter.encode_stream_event(event) for event in events)
    native_types = tuple(decode_sse(frame)[1]["type"] for frame in encoded)

    assert native_types == ("content_block_stop", "message_delta", "ping", "message_stop")
    assert tuple(adapter.decode_stream_event(frame) for frame in encoded) == (
        (events[0],),
        (events[1],),
        (events[2],),
        (events[3],),
    )


def test_claude_encodes_start_text_tool_finish_and_error_native_shapes() -> None:
    adapter = ClaudeAdapter()
    events = (
        StreamEvent(type="message_start", role="assistant", model="m"),
        StreamEvent(type="content_delta", index=1, text="Hi"),
        StreamEvent(type="tool_call_delta", index=2, tool_call_id="c", tool_name="f"),
        StreamEvent(type="tool_call_delta", index=2, arguments_delta='{"x":'),
        StreamEvent(type="message_end", finish_reason="length"),
        StreamEvent(type="error", metadata={"type": "overloaded_error"}),
    )

    native = tuple(decode_sse(adapter.encode_stream_event(event))[1] for event in events)

    assert native[0]["type"] == "message_start"
    assert native[0]["message"]["role"] == "assistant"
    assert native[1]["delta"] == {"type": "text_delta", "text": "Hi"}
    assert native[2]["content_block"]["type"] == "tool_use"
    assert native[3]["delta"] == {"type": "input_json_delta", "partial_json": '{"x":'}
    assert native[4]["delta"] == {"stop_reason": "max_tokens"}
    assert native[5] == {"type": "error", "error": {"type": "overloaded_error"}}


def test_gemini_combined_chunk_processes_all_parts_finish_and_usage() -> None:
    frame = _sse(
        {
            "modelVersion": "gemini-x",
            "candidates": [
                {
                    "index": 0,
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": "One"},
                            {"text": "Two"},
                            {"functionCall": {"id": "call_1", "name": "weather", "args": {"x": 1}}},
                        ],
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
        }
    )

    assert GeminiAdapter().decode_stream_event(frame) == (
        StreamEvent(type="content_delta", text="One", model="gemini-x"),
        StreamEvent(type="content_delta", text="Two", model="gemini-x"),
        StreamEvent(
            type="tool_call_delta",
            tool_call_id="call_1",
            tool_name="weather",
            arguments_delta='{"x":1}',
            model="gemini-x",
        ),
        StreamEvent(type="message_end", finish_reason="tool_call", model="gemini-x"),
        StreamEvent(type="usage", usage=CanonicalUsage(3, 4), model="gemini-x"),
    )


def test_gemini_connection_terminal_uses_empty_frame_not_stop_candidate() -> None:
    adapter = GeminiAdapter()
    done = StreamEvent(type="done")
    message_end = StreamEvent(type="message_end", finish_reason="stop")

    assert adapter.encode_stream_event(done) == b""
    assert adapter.decode_stream_event(b"") == (done,)
    assert adapter.encode_stream_event(message_end)
    assert adapter.decode_stream_event(adapter.encode_stream_event(message_end)) == (message_end,)


def test_gemini_stream_error_is_not_a_candidate() -> None:
    adapter = GeminiAdapter()
    event = StreamEvent(type="error", metadata={"code": 503, "message": "unavailable"})

    assert adapter.decode_stream_event(
        _sse({"error": {"code": 503, "message": "unavailable"}})
    ) == (event,)
    encoded = adapter.encode_stream_event(event)
    assert decode_sse(encoded)[1] == {"error": {"code": 503, "message": "unavailable"}}


def test_gemini_encodes_content_tool_finish_and_usage_native_shapes() -> None:
    adapter = GeminiAdapter()
    events = (
        StreamEvent(type="content_delta", text="Hi", model="m"),
        StreamEvent(
            type="tool_call_delta",
            tool_call_id="c",
            tool_name="f",
            arguments_delta='{"x":1}',
            model="m",
        ),
        StreamEvent(type="message_end", finish_reason="length", model="m"),
        StreamEvent(type="usage", usage=CanonicalUsage(2, 3), model="m"),
    )

    native = tuple(decode_sse(adapter.encode_stream_event(event))[1] for event in events)

    assert native[0]["candidates"][0]["content"]["parts"] == [{"text": "Hi"}]
    assert native[1]["candidates"][0]["content"]["parts"] == [
        {"functionCall": {"name": "f", "args": {"x": 1}, "id": "c"}}
    ]
    assert native[2]["candidates"][0]["finishReason"] == "MAX_TOKENS"
    assert native[3]["candidates"] == []
    assert native[3]["usageMetadata"]["candidatesTokenCount"] == 3
