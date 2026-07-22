from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from time import monotonic

import httpx
import orjson

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import CanonicalUsage, StreamEvent


class IncompleteStreamError(ValueError):
    """The provider reached EOF without a complete semantic stream terminal."""


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """One complete Server-Sent Event with its original wire representation."""

    data: bytes
    raw: bytes
    event: str | None = None
    event_id: str | None = None
    comment: bytes | None = None

    @property
    def is_heartbeat(self) -> bool:
        return self.comment is not None and not self.data and self.event is None

    @property
    def decoder_frame(self) -> bytes:
        return self.raw[3:] if self.raw.startswith(b"\xef\xbb\xbf") else self.raw


class SSEDecoder:
    """Incrementally split arbitrary HTTP byte chunks into complete SSE frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._first_frame = True

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        self._buffer.extend(chunk)
        events: list[SSEEvent] = []
        while (frame_end := self._frame_end()) is not None:
            raw = bytes(self._buffer[:frame_end])
            del self._buffer[:frame_end]
            event = self._decode_frame(raw)
            if event is not None:
                events.append(event)
            self._first_frame = False
        return events

    def finish(self) -> list[SSEEvent]:
        """Dispatch a final unterminated event when the HTTP body reaches EOF."""

        if not self._buffer:
            return []
        raw = bytes(self._buffer)
        self._buffer.clear()
        event = self._decode_frame(raw)
        self._first_frame = False
        return [] if event is None else [event]

    def _frame_end(self) -> int | None:
        line_start = 0
        while True:
            line_end = self._buffer.find(b"\n", line_start)
            if line_end < 0:
                return None
            line = self._buffer[line_start:line_end]
            if line.endswith(b"\r"):
                line = line[:-1]
            if not line:
                return line_end + 1
            line_start = line_end + 1

    def _decode_frame(self, raw: bytes) -> SSEEvent | None:
        data_lines: list[bytes] = []
        event_name: str | None = None
        event_id: str | None = None
        comments: list[bytes] = []
        saw_field = False

        lines = raw.splitlines()
        for index, original_line in enumerate(lines):
            line = original_line
            if self._first_frame and index == 0 and line.startswith(b"\xef\xbb\xbf"):
                line = line[3:]
            if not line:
                continue
            if line.startswith(b":"):
                comment = line[1:]
                comments.append(comment[1:] if comment.startswith(b" ") else comment)
                continue
            field, separator, value = line.partition(b":")
            if separator and value.startswith(b" "):
                value = value[1:]
            if field == b"data":
                data_lines.append(value)
                saw_field = True
            elif field == b"event":
                event_name = value.decode("utf-8", errors="replace")
                saw_field = True
            elif field == b"id" and b"\x00" not in value:
                event_id = value.decode("utf-8", errors="replace")
                saw_field = True

        if not saw_field and not comments:
            return None
        return SSEEvent(
            data=b"\n".join(data_lines),
            raw=raw,
            event=event_name,
            event_id=event_id,
            comment=b"\n".join(comments) if comments else None,
        )


@dataclass(slots=True)
class GatewayContext:
    """Mutable observations retained for exactly one upstream response stream."""

    source_protocol: Protocol
    target_protocol: Protocol
    initial_input_tokens: int | None = None
    audit_body_limit_bytes: int = 1_048_576
    started_at: float = field(default_factory=monotonic)
    observed_usage: CanonicalUsage | None = None
    provider_usage_complete: bool = False
    semantic_finish_observed: bool = False
    terminal_done_observed: bool = False
    first_token_ms: int | None = None
    emitted_any: bool = False
    error_observed: bool = False
    gemini_eof_decodes: int = 0
    _estimated_output_utf8_bytes: int = field(default=0, init=False, repr=False)
    _audit_preview: bytearray = field(default_factory=bytearray, init=False, repr=False)

    @property
    def audit_preview(self) -> bytes:
        return bytes(self._audit_preview)

    @property
    def estimated_output_tokens(self) -> int:
        """Return a fragmentation-independent estimate using one token per four UTF-8 bytes."""

        return (self._estimated_output_utf8_bytes + 3) // 4

    def observe(self, event: StreamEvent) -> None:
        if event.type == "error":
            self.error_observed = True
        elif event.type == "message_end":
            self.semantic_finish_observed = True
        elif event.type == "done":
            self.terminal_done_observed = True
        if event.usage is not None:
            self._merge_usage(event.usage)
            if event.type == "usage":
                self.provider_usage_complete = True
        content = ""
        if event.type == "content_delta" and event.text:
            content = event.text
        elif event.type == "tool_call_delta":
            content = "".join(
                part
                for part in (event.tool_call_id, event.tool_name, event.arguments_delta)
                if part
            )
        self._observe_content(content)

    def observe_passthrough(self, event: SSEEvent) -> None:
        """Collect metrics without making exact same-protocol forwarding depend on adapters."""

        if event.is_heartbeat:
            return
        if self.source_protocol is Protocol.OPENAI and event.data == b"[DONE]":
            self.semantic_finish_observed = True
            self.terminal_done_observed = True
            return
        try:
            payload = orjson.loads(event.data)
        except orjson.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        if "error" in payload or payload.get("type") == "error":
            self.error_observed = True
        content = ""
        usage: CanonicalUsage | None = None
        if self.source_protocol is Protocol.OPENAI:
            native_usage = payload.get("usage")
            if isinstance(native_usage, dict):
                input_tokens = native_usage.get("prompt_tokens")
                output_tokens = native_usage.get("completion_tokens")
                if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                    usage = CanonicalUsage(input_tokens, output_tokens)
                    self.provider_usage_complete = True
            choices = payload.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    if isinstance(delta.get("content"), str):
                        content += delta["content"]
                    tool_calls = delta.get("tool_calls")
                    if isinstance(tool_calls, list):
                        for call in tool_calls:
                            if isinstance(call, dict) and isinstance(call.get("id"), str):
                                content += call["id"]
                            function = call.get("function") if isinstance(call, dict) else None
                            if isinstance(function, dict):
                                for key in ("name", "arguments"):
                                    if isinstance(function.get(key), str):
                                        content += function[key]
        elif self.source_protocol is Protocol.CLAUDE:
            event_type = payload.get("type")
            if event_type == "message_stop":
                self.semantic_finish_observed = True
                self.terminal_done_observed = True
            if event_type == "message_start" and isinstance(payload.get("message"), dict):
                native_usage = payload["message"].get("usage")
                if isinstance(native_usage, dict) and isinstance(
                    native_usage.get("input_tokens"), int
                ):
                    usage = CanonicalUsage(native_usage["input_tokens"], 0)
            elif event_type == "message_delta" and isinstance(payload.get("usage"), dict):
                output_tokens = payload["usage"].get("output_tokens")
                if isinstance(output_tokens, int):
                    input_tokens = (
                        self.observed_usage.input_tokens if self.observed_usage is not None else 0
                    )
                    usage = CanonicalUsage(input_tokens, output_tokens)
                    self.provider_usage_complete = True
            delta = payload.get("delta")
            if isinstance(delta, dict):
                for key in ("text", "partial_json"):
                    if isinstance(delta.get(key), str):
                        content += delta[key]
            block = payload.get("content_block")
            if isinstance(block, dict) and block.get("type") == "tool_use":
                for key in ("name", "id"):
                    if isinstance(block.get(key), str):
                        content += block[key]
        else:
            native_usage = payload.get("usageMetadata")
            if isinstance(native_usage, dict):
                input_tokens = native_usage.get("promptTokenCount")
                output_tokens = native_usage.get("candidatesTokenCount")
                if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                    usage = CanonicalUsage(input_tokens, output_tokens)
                    self.provider_usage_complete = True
            candidates = payload.get("candidates")
            if isinstance(candidates, list):
                for candidate in candidates:
                    if isinstance(candidate, dict) and isinstance(
                        candidate.get("finishReason"), str
                    ):
                        finish_reason = candidate["finishReason"]
                        if finish_reason and finish_reason != "FINISH_REASON_UNSPECIFIED":
                            self.semantic_finish_observed = True
                            self.terminal_done_observed = True
                    native_content = (
                        candidate.get("content") if isinstance(candidate, dict) else None
                    )
                    parts = (
                        native_content.get("parts") if isinstance(native_content, dict) else None
                    )
                    if not isinstance(parts, list):
                        continue
                    for part in parts:
                        if not isinstance(part, dict):
                            continue
                        if isinstance(part.get("text"), str):
                            content += part["text"]
                        call = part.get("functionCall")
                        if isinstance(call, dict):
                            for key in ("id", "name"):
                                if isinstance(call.get(key), str):
                                    content += call[key]
                            if isinstance(call.get("args"), dict):
                                content += orjson.dumps(call["args"]).decode()
        if usage is not None:
            self._merge_usage(usage)
        self._observe_content(content)

    def _merge_usage(self, usage: CanonicalUsage) -> None:
        if self.observed_usage is None:
            self.observed_usage = usage
            return
        self.observed_usage = CanonicalUsage(
            input_tokens=max(self.observed_usage.input_tokens, usage.input_tokens),
            output_tokens=max(self.observed_usage.output_tokens, usage.output_tokens),
        )

    def estimated_usage(self) -> CanonicalUsage:
        input_tokens = (
            self.observed_usage.input_tokens
            if self.observed_usage is not None
            else (self.initial_input_tokens or 0)
        )
        return CanonicalUsage(input_tokens, self.estimated_output_tokens)

    def _observe_content(self, content: str) -> None:
        if not content:
            return
        self._estimated_output_utf8_bytes += len(content.encode("utf-8"))
        if self.first_token_ms is None:
            self.first_token_ms = max(0, round((monotonic() - self.started_at) * 1000))

    def record_output(self, chunk: bytes) -> None:
        if not chunk:
            return
        self.emitted_any = True
        remaining = self.audit_body_limit_bytes - len(self._audit_preview)
        if remaining > 0:
            self._audit_preview.extend(chunk[:remaining])


async def stream_gateway_response(
    context: GatewayContext,
    upstream: httpx.Response,
) -> AsyncIterator[bytes]:
    """Forward or convert one SSE response without buffering the response body."""

    source_adapter = get_adapter(context.source_protocol)
    target_adapter = get_adapter(context.target_protocol)
    stream_decoder = source_adapter.create_stream_decoder()
    stream_encoder = target_adapter.create_stream_encoder()
    parser = SSEDecoder()
    pending_done: StreamEvent | None = None
    if context.target_protocol is Protocol.CLAUDE and context.initial_input_tokens is not None:
        stream_encoder.set_initial_usage(context.initial_input_tokens)

    async def decode_native(event: SSEEvent) -> tuple[StreamEvent, ...]:
        if event.is_heartbeat:
            return (StreamEvent(type="heartbeat"),)
        return stream_decoder.decode(event.decoder_frame)

    def encode_canonical(event: StreamEvent) -> tuple[bytes, ...]:
        nonlocal pending_done
        context.observe(event)
        if event.usage is not None and context.observed_usage is not None:
            event = replace(event, usage=context.observed_usage)
        if event.type == "done":
            if pending_done is None:
                pending_done = event
            return ()
        return tuple(frame for frame in stream_encoder.encode(event) if frame)

    async def convert_native(event: SSEEvent) -> tuple[bytes, ...]:
        frames: list[bytes] = []
        for canonical_event in await decode_native(event):
            frames.extend(encode_canonical(canonical_event))
        return tuple(frames)

    try:
        async for chunk in upstream.aiter_bytes():
            native_events = parser.feed(chunk)
            if context.source_protocol is context.target_protocol:
                for native_event in native_events:
                    context.observe_passthrough(native_event)
                context.record_output(chunk)
                yield chunk
                continue
            for native_event in native_events:
                for frame in await convert_native(native_event):
                    context.record_output(frame)
                    yield frame
        terminal_frames: list[bytes] = []
        for native_event in parser.finish():
            if context.source_protocol is context.target_protocol:
                context.observe_passthrough(native_event)
            else:
                terminal_frames.extend(await convert_native(native_event))

        if context.source_protocol is Protocol.GEMINI:
            context.gemini_eof_decodes += 1
            for canonical_event in stream_decoder.decode(b""):
                if context.source_protocol is context.target_protocol:
                    context.observe(canonical_event)
                    continue
                terminal_frames.extend(encode_canonical(canonical_event))
        if context.source_protocol is context.target_protocol:
            if not context.semantic_finish_observed:
                raise IncompleteStreamError(
                    "The upstream provider reached EOF without its native terminal event"
                )
            return
        if not context.semantic_finish_observed:
            raise IncompleteStreamError(
                "The upstream provider reached EOF without a semantic finish event"
            )
        if pending_done is None:
            pending_done = StreamEvent(type="done")
            context.observe(pending_done)
        if not context.provider_usage_complete:
            estimated_usage = context.estimated_usage()
            terminal_frames.extend(
                stream_encoder.encode(StreamEvent(type="usage", usage=estimated_usage))
            )
        terminal_frames.extend(stream_encoder.encode(pending_done))
        for frame in terminal_frames:
            context.record_output(frame)
            yield frame
    finally:
        await upstream.aclose()
