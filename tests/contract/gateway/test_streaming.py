from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

import httpx
import orjson
import pytest

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import decode_sse
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import CanonicalUsage, StreamEvent
from ai_gateway.transport.sse import GatewayContext, SSEDecoder, stream_gateway_response


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: Iterable[bytes]) -> None:
        self.chunks = tuple(chunks)
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


def _sse(payload: dict[str, object], event: str | None = None) -> bytes:
    prefix = b"" if event is None else f"event: {event}\n".encode()
    return prefix + b"data: " + orjson.dumps(payload) + b"\n\n"


def _source_frames(protocol: Protocol) -> tuple[bytes, ...]:
    if protocol is Protocol.OPENAI:
        return (
            _sse({"model": "m", "choices": [{"index": 0, "delta": {"role": "assistant"}}]}),
            _sse({"model": "m", "choices": [{"index": 0, "delta": {"content": "Hi"}}]}),
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
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                }
            ),
            b"data: [DONE]\n\n",
        )
    if protocol is Protocol.CLAUDE:
        return (
            _sse(
                {
                    "type": "message_start",
                    "message": {"role": "assistant", "model": "m", "usage": {"input_tokens": 2}},
                },
                "message_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Hi"},
                },
                "content_block_delta",
            ),
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
        )
    return (
        _sse(
            {
                "modelVersion": "m",
                "candidates": [
                    {
                        "index": 0,
                        "content": {
                            "role": "model",
                            "parts": [
                                {"text": "Hi"},
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
    )


def _odd_chunks(wire: bytes) -> tuple[bytes, ...]:
    cuts = (1, 3, 8, 13, 21, 34, 55)
    points = [point for point in cuts if point < len(wire)]
    return tuple(wire[start:end] for start, end in zip((0, *points), (*points, len(wire))))


def _decode_output(protocol: Protocol, wire: bytes) -> tuple[StreamEvent, ...]:
    parser = SSEDecoder()
    native = [*parser.feed(wire), *parser.finish()]
    decoder = get_adapter(protocol).create_stream_decoder()
    events = [event for frame in native for event in decoder.decode(frame.raw)]
    if protocol is Protocol.GEMINI:
        events.extend(decoder.decode(b""))
    return tuple(events)


@pytest.mark.parametrize("source", list(Protocol))
@pytest.mark.parametrize("target", list(Protocol))
async def test_all_nine_stream_pairs_convert_incrementally(
    source: Protocol,
    target: Protocol,
) -> None:
    upstream_wire = b"".join(_source_frames(source))
    stream = ChunkStream(_odd_chunks(upstream_wire))
    response = httpx.Response(200, stream=stream)
    context = GatewayContext(
        source_protocol=source,
        target_protocol=target,
        initial_input_tokens=2,
        audit_body_limit_bytes=256,
    )

    chunks = [chunk async for chunk in stream_gateway_response(context, response)]
    output = b"".join(chunks)

    if source is target:
        assert output == upstream_wire
    else:
        events = _decode_output(target, output)
        assert "".join(event.text or "" for event in events) == "Hi"
        tools: dict[int, str] = {}
        for event in events:
            if event.type == "tool_call_delta" and event.tool_index is not None:
                tools[event.tool_index] = tools.get(event.tool_index, "") + (
                    event.arguments_delta or ""
                )
        assert {
            orjson.loads(arguments)[next(iter(orjson.loads(arguments)))]
            for arguments in tools.values()
        } == {1, 2}
        assert (
            next(event for event in events if event.type == "message_end").finish_reason
            == "tool_call"
        )
        assert next(event for event in events if event.type == "usage").usage == CanonicalUsage(
            2, 3
        )

    assert context.observed_usage == CanonicalUsage(2, 3)
    assert context.first_token_ms is not None
    assert len(context.audit_preview) <= 256
    assert stream.closed


async def test_claude_target_places_input_usage_on_start_and_output_on_final_delta() -> None:
    source = Protocol.OPENAI
    upstream_wire = b"".join(_source_frames(source))
    response = httpx.Response(200, stream=ChunkStream(_odd_chunks(upstream_wire)))
    context = GatewayContext(source, Protocol.CLAUDE, initial_input_tokens=2)

    output = b"".join([chunk async for chunk in stream_gateway_response(context, response)])
    bodies = [decode_sse(event.raw)[1] for event in SSEDecoder().feed(output)]

    assert bodies[0]["type"] == "message_start"
    assert bodies[0]["message"]["usage"] == {"input_tokens": 2}
    terminal = next(body for body in bodies if body["type"] == "message_delta")
    assert terminal["delta"]["stop_reason"] == "tool_use"
    assert terminal["usage"] == {"output_tokens": 3}
    assert bodies[-1]["type"] == "message_stop"


async def test_gemini_eof_terminal_is_not_confused_with_encoder_no_output() -> None:
    upstream_wire = b"".join(_source_frames(Protocol.GEMINI))
    response = httpx.Response(200, stream=ChunkStream(_odd_chunks(upstream_wire)))
    context = GatewayContext(Protocol.GEMINI, Protocol.OPENAI, initial_input_tokens=2)

    output = b"".join([chunk async for chunk in stream_gateway_response(context, response)])

    assert output.count(b"data: [DONE]\n\n") == 1
    assert context.gemini_eof_decodes == 1


async def test_same_protocol_forwards_opaque_heartbeat_and_vendor_frames_exactly() -> None:
    heartbeat = b": provider-heartbeat\r\n\r\n"
    opaque = b"event: vendor_extension\r\ndata: not-json\r\n\r\n"
    stream = ChunkStream((heartbeat, opaque))
    response = httpx.Response(200, stream=stream)
    context = GatewayContext(Protocol.OPENAI, Protocol.OPENAI)
    body = stream_gateway_response(context, response)

    assert await anext(body) == heartbeat
    assert context.first_token_ms is None
    assert await anext(body) == opaque
    with pytest.raises(StopAsyncIteration):
        await anext(body)

    assert context.audit_preview == heartbeat + opaque
    assert stream.closed
