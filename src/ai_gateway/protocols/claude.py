from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

import orjson

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import (
    ProtocolAdapter,
    StreamDecoder,
    StreamEncoder,
    UnsupportedFeatureError,
    add_vendor_scope,
    decode_sse,
    encode_sse,
    image_media_type,
    image_media_type_from_url,
    native_extensions,
    nonnegative_int,
    optional_float,
    optional_int,
    require_object,
    required_bool,
    string_list,
    thaw,
    validate_usage,
    vendor_metadata,
    vendor_scope,
)
from ai_gateway.protocols.types import (
    CanonicalMessage,
    CanonicalRequest,
    CanonicalResponse,
    CanonicalTool,
    CanonicalUsage,
    ContentPart,
    FinishReason,
    ImagePart,
    StreamEvent,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)

_REQUEST_FIELDS = {
    "model",
    "system",
    "messages",
    "tools",
    "tool_choice",
    "temperature",
    "top_p",
    "max_tokens",
    "stop_sequences",
    "stream",
}
_RESPONSE_FIELDS = {
    "id",
    "type",
    "role",
    "model",
    "content",
    "stop_reason",
    "stop_sequence",
    "usage",
}


class ClaudeAdapter(ProtocolAdapter):
    protocol = Protocol.CLAUDE

    def __init__(self, default_max_output_tokens: int = 4096) -> None:
        if default_max_output_tokens < 1:
            raise ValueError("default_max_output_tokens must be positive")
        self.default_max_output_tokens = default_max_output_tokens

    def decode_request(self, payload: Mapping[str, Any]) -> CanonicalRequest:
        model = payload.get("model")
        if not isinstance(model, str):
            raise UnsupportedFeatureError("model", "must be a string")
        messages_value = payload.get("messages", [])
        if not isinstance(messages_value, list):
            raise UnsupportedFeatureError("messages", "must be a list")
        messages: list[CanonicalMessage] = []
        system = list(_decode_content(payload.get("system"), "system"))
        if not all(isinstance(part, TextPart) for part in system):
            raise UnsupportedFeatureError("system", "must contain only text")
        for index, raw_message in enumerate(messages_value):
            message = require_object(raw_message, f"messages[{index}]")
            role = message.get("role")
            if role == "system":
                system_parts = _decode_content(
                    message.get("content"),
                    f"messages[{index}].content",
                    role=role,
                )
                if not all(isinstance(part, TextPart) for part in system_parts):
                    raise UnsupportedFeatureError(
                        f"messages[{index}].content",
                        "system content must contain only text",
                    )
                system.extend(system_parts)
                continue
            if role not in {"user", "assistant"}:
                raise UnsupportedFeatureError(
                    f"messages[{index}].role", f"unsupported role {role!r}"
                )
            messages.append(
                CanonicalMessage(
                    role=role,
                    content=_decode_content(
                        message.get("content"),
                        f"messages[{index}].content",
                        role=role,
                    ),
                    metadata=vendor_metadata(
                        self.protocol,
                        message,
                        {"role", "content"},
                    ),
                )
            )
        metadata = vendor_metadata(self.protocol, payload, _REQUEST_FIELDS)
        _capture_tool_choice_extensions(metadata, payload.get("tool_choice"))
        return CanonicalRequest(
            model=model,
            messages=messages,
            system=tuple(system),
            tools=_decode_tools(payload.get("tools")),
            tool_choice=_decode_tool_choice(payload.get("tool_choice")),
            temperature=optional_float(payload.get("temperature"), "temperature"),
            top_p=optional_float(payload.get("top_p"), "top_p"),
            max_output_tokens=optional_int(payload.get("max_tokens"), "max_tokens"),
            stop_sequences=string_list(payload.get("stop_sequences"), "stop_sequences"),
            stream=required_bool(payload.get("stream"), "stream"),
            metadata=metadata,
        )

    def encode_request(self, request: CanonicalRequest) -> dict[str, Any]:
        payload = native_extensions(self.protocol, request.metadata)
        payload["model"] = request.model
        if request.system:
            if not all(isinstance(part, TextPart) for part in request.system):
                raise UnsupportedFeatureError("system", "must contain only text")
            payload["system"] = _encode_content(request.system)
        payload["messages"] = [
            _encode_message(message, index) for index, message in enumerate(request.messages)
        ]
        if request.tools:
            payload["tools"] = [_encode_tool(tool) for tool in request.tools]
        if request.tool_choice is not None:
            payload["tool_choice"] = _encode_tool_choice(request.tool_choice, request.metadata)
        _set_optional(payload, "temperature", request.temperature)
        _set_optional(payload, "top_p", request.top_p)
        max_output_tokens = (
            self.default_max_output_tokens
            if request.max_output_tokens is None
            else request.max_output_tokens
        )
        if max_output_tokens < 1:
            raise UnsupportedFeatureError(
                "max_output_tokens", "must be positive when converting to Claude"
            )
        payload["max_tokens"] = max_output_tokens
        if request.stop_sequences:
            payload["stop_sequences"] = list(request.stop_sequences)
        payload["stream"] = request.stream
        return payload

    def decode_response(self, payload: Mapping[str, Any]) -> CanonicalResponse:
        if payload.get("role") != "assistant":
            raise UnsupportedFeatureError("role", "must be assistant")
        model = payload.get("model")
        return CanonicalResponse(
            model=model if isinstance(model, str) else "",
            message=CanonicalMessage(
                role="assistant",
                content=_decode_content(payload.get("content"), "content", role="assistant"),
            ),
            finish_reason=_decode_finish_reason(payload.get("stop_reason")),
            usage=_decode_usage(payload.get("usage")),
            metadata=vendor_metadata(
                self.protocol,
                payload,
                _RESPONSE_FIELDS,
                response_id=payload.get("id"),
                stop_sequence=payload.get("stop_sequence"),
            ),
        )

    def encode_response(self, response: CanonicalResponse) -> dict[str, Any]:
        if response.message.role != "assistant":
            raise UnsupportedFeatureError("message.role", "must be assistant")
        payload = native_extensions(self.protocol, response.metadata)
        payload.update(
            {
                "id": response.metadata.get("response_id", "msg_gateway"),
                "type": "message",
                "role": "assistant",
                "model": response.model,
                "content": _encode_content(
                    response.message.content,
                    "message.content",
                    role="assistant",
                ),
                "stop_reason": _encode_finish_reason(response.finish_reason),
                "stop_sequence": response.metadata.get("stop_sequence"),
            }
        )
        if response.usage is not None:
            validate_usage(response.usage)
            payload["usage"] = _encode_usage(response.usage)
        return payload

    def create_stream_decoder(self) -> StreamDecoder:
        return _ClaudeStreamDecoder()

    def create_stream_encoder(self) -> StreamEncoder:
        return _ClaudeStreamEncoder(self)

    def decode_stream_event(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        return self.create_stream_decoder().decode(event)

    def _decode_isolated_stream_event(
        self, event: bytes | Mapping[str, Any]
    ) -> tuple[StreamEvent, ...]:
        event_name, raw_payload = decode_sse(event)
        payload = require_object(raw_payload, "stream_event.data")
        event_type = payload.get("type", event_name)
        if event_type == "content_block_delta":
            delta = require_object(payload.get("delta"), "stream_event.delta")
            index = nonnegative_int(payload.get("index", 0), "stream_event.index")
            event_metadata = vendor_metadata(
                self.protocol,
                payload,
                {"type", "index", "delta"},
            )
            add_vendor_scope(
                event_metadata,
                self.protocol,
                "__delta__",
                {
                    key: item
                    for key, item in delta.items()
                    if key not in {"type", "text", "partial_json"}
                },
            )
            if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                return (
                    StreamEvent(
                        type="content_delta",
                        index=index,
                        text=delta["text"],
                        metadata=event_metadata,
                    ),
                )
            if delta.get("type") == "input_json_delta":
                partial_json = delta.get("partial_json")
                return (
                    StreamEvent(
                        type="tool_call_delta",
                        index=index,
                        arguments_delta=(partial_json if isinstance(partial_json, str) else None),
                        metadata=event_metadata,
                    ),
                )
            raise UnsupportedFeatureError(
                "stream_event.delta.type", f"unsupported delta {delta.get('type')!r}"
            )
        if event_type == "content_block_start":
            block = require_object(payload.get("content_block"), "stream_event.content_block")
            index = nonnegative_int(payload.get("index", 0), "stream_event.index")
            event_metadata = vendor_metadata(
                self.protocol,
                payload,
                {"type", "index", "content_block"},
            )
            add_vendor_scope(
                event_metadata,
                self.protocol,
                "__content_block__",
                {
                    key: item
                    for key, item in block.items()
                    if key not in {"type", "text", "id", "name", "input"}
                },
            )
            if block.get("type") == "tool_use":
                arguments = block.get("input", {})
                arguments = require_object(arguments, "stream_event.content_block.input")
                return (
                    StreamEvent(
                        type="tool_call_delta",
                        index=index,
                        tool_call_id=(
                            block.get("id") if isinstance(block.get("id"), str) else None
                        ),
                        tool_name=(
                            block.get("name") if isinstance(block.get("name"), str) else None
                        ),
                        arguments_delta=(orjson.dumps(arguments).decode() if arguments else None),
                        content_type="tool_call",
                        metadata=event_metadata,
                    ),
                )
            if block.get("type") == "text":
                text = block.get("text", "")
                if not isinstance(text, str):
                    raise UnsupportedFeatureError(
                        "stream_event.content_block.text", "must be a string"
                    )
                events = [
                    StreamEvent(
                        type="content_start",
                        index=index,
                        content_type="text",
                        metadata=event_metadata,
                    )
                ]
                if text:
                    events.append(
                        StreamEvent(
                            type="content_delta",
                            index=index,
                            text=text,
                            content_type="text",
                        )
                    )
                return tuple(events)
            raise UnsupportedFeatureError(
                "stream_event.content_block.type",
                f"unsupported block {block.get('type')!r}",
            )
        if event_type == "content_block_stop":
            index = nonnegative_int(payload.get("index", 0), "stream_event.index")
            return (
                StreamEvent(
                    type="content_end",
                    index=index,
                    metadata=vendor_metadata(
                        self.protocol,
                        payload,
                        {"type", "index"},
                    ),
                ),
            )
        if event_type == "message_start":
            message = require_object(payload.get("message", {}), "stream_event.message")
            model = message.get("model") if isinstance(message.get("model"), str) else None
            usage = _decode_usage(message.get("usage"))
            event_metadata = vendor_metadata(
                self.protocol,
                payload,
                {"type", "message"},
            )
            add_vendor_scope(
                event_metadata,
                self.protocol,
                "__message__",
                {
                    key: item
                    for key, item in message.items()
                    if key not in {"type", "role", "model", "content", "usage"}
                },
            )
            return (
                StreamEvent(
                    type="message_start",
                    role="assistant",
                    model=model,
                    usage=usage,
                    metadata=event_metadata,
                ),
            )
        if event_type == "message_delta":
            delta = require_object(payload.get("delta", {}), "stream_event.delta")
            event_metadata = vendor_metadata(
                self.protocol,
                payload,
                {"type", "delta", "usage"},
            )
            add_vendor_scope(
                event_metadata,
                self.protocol,
                "__message_delta__",
                {
                    key: item
                    for key, item in delta.items()
                    if key not in {"stop_reason", "stop_sequence"}
                },
            )
            events = []
            stop_reason = delta.get("stop_reason")
            if stop_reason is not None:
                events.append(
                    StreamEvent(
                        type="message_end",
                        finish_reason=_decode_finish_reason(stop_reason),
                        metadata=event_metadata,
                    )
                )
            usage = _decode_usage(payload.get("usage"))
            if usage is not None:
                events.append(StreamEvent(type="usage", usage=usage, metadata=event_metadata))
            if not events:
                raise UnsupportedFeatureError(
                    "stream_event", "message_delta contains neither stop reason nor usage"
                )
            return tuple(events)
        if event_type == "message_stop":
            return (
                StreamEvent(
                    type="done",
                    metadata=vendor_metadata(self.protocol, payload, {"type"}),
                ),
            )
        if event_type == "ping":
            return (
                StreamEvent(
                    type="heartbeat",
                    metadata=vendor_metadata(self.protocol, payload, {"type"}),
                ),
            )
        if event_type == "error":
            error = require_object(payload.get("error", payload), "stream_event.error")
            metadata = {
                key: thaw(item)
                for key, item in error.items()
                if key in {"type", "message", "code", "status"}
            }
            metadata.update(vendor_metadata(self.protocol, payload, {"type", "error"}))
            add_vendor_scope(
                metadata,
                self.protocol,
                "__error__",
                {
                    key: item
                    for key, item in error.items()
                    if key not in {"type", "message", "code", "status"}
                },
            )
            return (
                StreamEvent(
                    type="error",
                    metadata=metadata,
                ),
            )
        raise UnsupportedFeatureError(
            "stream_event.type", f"unsupported Claude event {event_type!r}"
        )

    def encode_stream_event(self, event: StreamEvent) -> bytes:
        if event.type == "content_start":
            payload = {
                "type": "content_block_start",
                "index": event.index,
                "content_block": {"type": "text", "text": ""},
            }
        elif event.type == "content_delta":
            payload = {
                "type": "content_block_delta",
                "index": event.index,
                "delta": {"type": "text_delta", "text": event.text or ""},
            }
        elif event.type == "tool_call_delta":
            if event.tool_call_id is not None or event.tool_name is not None:
                arguments: dict[str, Any] = {}
                if event.arguments_delta:
                    try:
                        raw_arguments = orjson.loads(event.arguments_delta)
                    except orjson.JSONDecodeError as exc:
                        raise UnsupportedFeatureError(
                            "stream_event.arguments_delta",
                            "Claude tool starts require complete JSON arguments",
                        ) from exc
                    arguments = require_object(raw_arguments, "stream_event.arguments_delta")
                payload = {
                    "type": "content_block_start",
                    "index": event.index,
                    "content_block": {
                        "type": "tool_use",
                        "id": event.tool_call_id or "",
                        "name": event.tool_name or "",
                        "input": arguments,
                    },
                }
            else:
                payload = {
                    "type": "content_block_delta",
                    "index": event.index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": event.arguments_delta or "",
                    },
                }
        elif event.type == "message_start":
            message: dict[str, Any] = {
                "type": "message",
                "role": "assistant",
                "model": event.model or "",
                "content": [],
            }
            if event.usage is not None:
                message["usage"] = _encode_usage(event.usage)
            payload = {
                "type": "message_start",
                "message": message,
            }
        elif event.type == "message_end":
            if event.finish_reason is None:
                raise UnsupportedFeatureError("stream_event.finish_reason", "is required")
            payload = {
                "type": "message_delta",
                "delta": {"stop_reason": _encode_finish_reason(event.finish_reason)},
            }
        elif event.type == "content_end":
            payload = {"type": "content_block_stop", "index": event.index}
        elif event.type == "done":
            payload = {"type": "message_stop"}
        elif event.type == "error":
            payload = {"type": "error", "error": thaw(event.metadata)}
        elif event.type == "heartbeat":
            payload = {"type": "ping"}
        elif event.type == "usage":
            raise UnsupportedFeatureError(
                "stream_event.usage",
                "Claude usage requires a stateful encoder to place input and output tokens",
            )
        else:
            raise UnsupportedFeatureError("stream_event.type", f"cannot encode {event.type!r}")
        return encode_sse(payload, str(payload["type"]))


class _ClaudeStreamDecoder(StreamDecoder):
    def __init__(self) -> None:
        self._adapter = ClaudeAdapter()
        self._block_types: dict[int, str] = {}
        self._tool_indices: dict[int, int] = {}
        self._next_tool_index = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cache_read_tokens = 0
        self._cache_write_tokens = 0
        self._saw_usage = False
        self._usage_emitted = False

    def _close_open_blocks(self) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        for index in sorted(self._block_types):
            content_type = self._block_types[index]
            events.append(
                StreamEvent(
                    type="content_end",
                    index=index,
                    tool_index=self._tool_indices.get(index),
                    content_type=content_type,  # type: ignore[arg-type]
                )
            )
        self._block_types.clear()
        self._tool_indices.clear()
        return events

    def decode(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        raw_events = self._adapter._decode_isolated_stream_event(event)
        events: list[StreamEvent] = []
        terminal = any(raw.type == "message_end" for raw in raw_events)
        done = any(raw.type == "done" for raw in raw_events)
        usage_metadata: Mapping[str, Any] = {}
        for raw in raw_events:
            if raw.type == "message_start":
                if raw.usage is not None:
                    self._input_tokens = raw.usage.input_tokens
                    self._output_tokens = raw.usage.output_tokens
                    self._cache_read_tokens = raw.usage.cache_read_tokens
                    self._cache_write_tokens = raw.usage.cache_write_tokens
                    self._saw_usage = True
                events.append(raw)
            elif raw.type == "usage":
                if raw.usage is not None:
                    if raw.usage.input_tokens:
                        self._input_tokens = raw.usage.input_tokens
                    if raw.usage.cache_read_tokens:
                        self._cache_read_tokens = raw.usage.cache_read_tokens
                    if raw.usage.cache_write_tokens:
                        self._cache_write_tokens = raw.usage.cache_write_tokens
                    self._output_tokens = raw.usage.output_tokens
                    self._saw_usage = True
                    usage_metadata = raw.metadata
            elif raw.type == "content_start":
                self._block_types[raw.index] = "text"
                events.append(raw)
            elif raw.type == "content_delta":
                if raw.index not in self._block_types:
                    self._block_types[raw.index] = "text"
                    events.append(
                        StreamEvent(type="content_start", index=raw.index, content_type="text")
                    )
                events.append(replace(raw, content_type="text"))
            elif raw.type == "tool_call_delta":
                tool_index = self._tool_indices.get(raw.index)
                if tool_index is None:
                    tool_index = self._next_tool_index
                    self._next_tool_index += 1
                    self._tool_indices[raw.index] = tool_index
                    self._block_types[raw.index] = "tool_call"
                events.append(replace(raw, tool_index=tool_index, content_type="tool_call"))
            elif raw.type == "content_end":
                content_type = self._block_types.pop(raw.index, None)
                tool_index = self._tool_indices.pop(raw.index, None)
                events.append(
                    replace(
                        raw,
                        content_type=content_type,  # type: ignore[arg-type]
                        tool_index=tool_index,
                    )
                )
            elif raw.type in {"message_end", "done"}:
                events.extend(self._close_open_blocks())
                events.append(raw)
            else:
                events.append(raw)
        if (terminal or done) and self._saw_usage and not self._usage_emitted:
            usage_event = StreamEvent(
                type="usage",
                usage=CanonicalUsage(
                    self._input_tokens,
                    self._output_tokens,
                    self._cache_read_tokens,
                    self._cache_write_tokens,
                ),
                metadata=usage_metadata,
            )
            if done and events and events[-1].type == "done":
                events.insert(len(events) - 1, usage_event)
            else:
                events.append(usage_event)
            self._usage_emitted = True
        return tuple(events)


class _ClaudeStreamEncoder(StreamEncoder):
    def __init__(self, adapter: ClaudeAdapter) -> None:
        self._adapter = adapter
        self._block_indices: dict[tuple[str, object], int] = {}
        self._open_blocks: dict[int, str] = {}
        self._used_indices: set[int] = set()
        self._input_tokens: int | None = None
        self._output_tokens: int | None = None
        self._cache_read_tokens = 0
        self._cache_write_tokens = 0
        self._pending_end: StreamEvent | None = None
        self._usage_metadata: Mapping[str, Any] = {}

    def set_initial_usage(self, input_tokens: int) -> None:
        self._input_tokens = nonnegative_int(input_tokens, "stream_event.usage.input_tokens")

    def _key(self, event: StreamEvent, content_type: str) -> tuple[str, object]:
        if content_type == "tool_call":
            identity: object = (
                event.tool_index
                if event.tool_index is not None
                else event.tool_call_id
                if event.tool_call_id is not None
                else event.index
            )
            return (content_type, identity)
        return (content_type, event.index)

    def _index_for(self, event: StreamEvent, content_type: str) -> int:
        key = self._key(event, content_type)
        existing = self._block_indices.get(key)
        if existing is not None:
            return existing
        index = event.index
        if index in self._used_indices:
            index = 0
            while index in self._used_indices:
                index += 1
        self._block_indices[key] = index
        self._used_indices.add(index)
        return index

    @staticmethod
    def _frame(payload: Mapping[str, Any]) -> bytes:
        return encode_sse(payload, str(payload["type"]))

    def _message_start_frame(self, event: StreamEvent) -> bytes:
        payload = native_extensions(Protocol.CLAUDE, event.metadata)
        message = vendor_scope(Protocol.CLAUDE, event.metadata, "__message__")
        message.update(
            {
                "type": "message",
                "role": "assistant",
                "model": event.model or "",
                "content": [],
            }
        )
        if event.usage is not None:
            validate_usage(event.usage, "stream_event.usage")
            self._input_tokens = event.usage.input_tokens
            self._cache_read_tokens = event.usage.cache_read_tokens
            self._cache_write_tokens = event.usage.cache_write_tokens
        if self._input_tokens is not None:
            usage = {"input_tokens": self._input_tokens}
            if self._cache_read_tokens or self._cache_write_tokens:
                usage.update(
                    {
                        "cache_read_input_tokens": self._cache_read_tokens,
                        "cache_creation_input_tokens": self._cache_write_tokens,
                    }
                )
            message["usage"] = usage
        payload.update({"type": "message_start", "message": message})
        return self._frame(payload)

    def _terminal_frame(self) -> bytes | None:
        event = self._pending_end
        if event is None:
            return None
        if event.finish_reason is None:
            raise UnsupportedFeatureError("stream_event.finish_reason", "is required")
        payload = native_extensions(Protocol.CLAUDE, event.metadata)
        delta = vendor_scope(Protocol.CLAUDE, event.metadata, "__message_delta__")
        delta["stop_reason"] = _encode_finish_reason(event.finish_reason)
        payload.update({"type": "message_delta", "delta": delta})
        if self._output_tokens is not None:
            usage = vendor_scope(Protocol.CLAUDE, self._usage_metadata, "__usage__")
            usage["output_tokens"] = self._output_tokens
            payload["usage"] = usage
        self._pending_end = None
        return self._frame(payload)

    def _start_text(
        self, event: StreamEvent, *, preserve_metadata: bool
    ) -> tuple[int, bytes | None]:
        index = self._index_for(event, "text")
        if index in self._open_blocks:
            return index, None
        self._open_blocks[index] = "text"
        payload = native_extensions(Protocol.CLAUDE, event.metadata) if preserve_metadata else {}
        block = (
            vendor_scope(Protocol.CLAUDE, event.metadata, "__content_block__")
            if preserve_metadata
            else {}
        )
        block.update({"type": "text", "text": ""})
        payload.update({"type": "content_block_start", "index": index, "content_block": block})
        return index, self._frame(payload)

    def _start_tool(self, event: StreamEvent) -> tuple[int, bytes | None]:
        index = self._index_for(event, "tool_call")
        if index in self._open_blocks:
            return index, None
        if event.tool_call_id is None or event.tool_name is None:
            raise UnsupportedFeatureError(
                "stream_event.tool_call",
                "Claude requires id and name before tool argument deltas",
            )
        self._open_blocks[index] = "tool_call"
        payload = native_extensions(Protocol.CLAUDE, event.metadata)
        block = vendor_scope(Protocol.CLAUDE, event.metadata, "__content_block__")
        block.update(
            {
                "type": "tool_use",
                "id": event.tool_call_id,
                "name": event.tool_name,
                "input": {},
            }
        )
        payload.update({"type": "content_block_start", "index": index, "content_block": block})
        return index, self._frame(payload)

    def _close_index(self, index: int, metadata: Mapping[str, Any] | None = None) -> bytes | None:
        if self._open_blocks.pop(index, None) is None:
            return None
        payload = native_extensions(Protocol.CLAUDE, metadata or {})
        payload.update({"type": "content_block_stop", "index": index})
        return self._frame(payload)

    def _close_all(self) -> list[bytes]:
        frames = []
        for index in sorted(self._open_blocks):
            frame = self._close_index(index)
            if frame is not None:
                frames.append(frame)
        return frames

    def _close_type(self, content_type: str) -> list[bytes]:
        frames = []
        for index, open_type in list(self._open_blocks.items()):
            if open_type != content_type:
                continue
            frame = self._close_index(index)
            if frame is not None:
                frames.append(frame)
        return frames

    def encode(self, event: StreamEvent) -> tuple[bytes, ...]:
        frames: list[bytes] = []
        if event.type == "message_start":
            frames.append(self._message_start_frame(event))
        elif event.type == "content_start":
            _, start = self._start_text(event, preserve_metadata=True)
            if start is not None:
                frames.append(start)
        elif event.type == "content_delta":
            index, start = self._start_text(event, preserve_metadata=False)
            if start is not None:
                frames.append(start)
            payload = native_extensions(Protocol.CLAUDE, event.metadata)
            delta = vendor_scope(Protocol.CLAUDE, event.metadata, "__delta__")
            delta.update({"type": "text_delta", "text": event.text or ""})
            payload.update(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": delta,
                }
            )
            frames.append(self._frame(payload))
        elif event.type == "tool_call_delta":
            frames.extend(self._close_type("text"))
            index, start = self._start_tool(event)
            if start is not None:
                frames.append(start)
            if event.arguments_delta:
                payload = native_extensions(Protocol.CLAUDE, event.metadata)
                delta = vendor_scope(Protocol.CLAUDE, event.metadata, "__delta__")
                delta.update(
                    {
                        "type": "input_json_delta",
                        "partial_json": event.arguments_delta,
                    }
                )
                payload.update(
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": delta,
                    }
                )
                frames.append(self._frame(payload))
        elif event.type == "content_end":
            content_type = event.content_type or "text"
            block_index = self._block_indices.get(self._key(event, content_type))
            if block_index is not None:
                frame = self._close_index(block_index, event.metadata)
                if frame is not None:
                    frames.append(frame)
        elif event.type == "message_end":
            frames.extend(self._close_all())
            self._pending_end = event
            if self._output_tokens is not None:
                frame = self._terminal_frame()
                if frame is not None:
                    frames.append(frame)
        elif event.type == "usage":
            if event.usage is None:
                raise UnsupportedFeatureError("stream_event.usage", "is required")
            validate_usage(event.usage, "stream_event.usage")
            if self._input_tokens is None:
                self._input_tokens = event.usage.input_tokens
                self._cache_read_tokens = event.usage.cache_read_tokens
                self._cache_write_tokens = event.usage.cache_write_tokens
            self._output_tokens = event.usage.output_tokens
            self._usage_metadata = event.metadata
            frame = self._terminal_frame()
            if frame:
                frames.append(frame)
        elif event.type == "done":
            frames.extend(self._close_all())
            terminal = self._terminal_frame()
            if terminal is not None:
                frames.append(terminal)
            payload = native_extensions(Protocol.CLAUDE, event.metadata)
            payload["type"] = "message_stop"
            frames.append(self._frame(payload))
        elif event.type == "heartbeat":
            payload = native_extensions(Protocol.CLAUDE, event.metadata)
            payload["type"] = "ping"
            frames.append(self._frame(payload))
        elif event.type == "error":
            payload = native_extensions(Protocol.CLAUDE, event.metadata)
            error = {
                key: thaw(item)
                for key, item in event.metadata.items()
                if key != "vendor_extensions"
            }
            error.update(vendor_scope(Protocol.CLAUDE, event.metadata, "__error__"))
            payload.update({"type": "error", "error": error})
            frames.append(self._frame(payload))
        else:
            frame = self._adapter.encode_stream_event(event)
            if frame:
                frames.append(frame)
        return tuple(frames)


def _decode_content(
    value: Any,
    field: str,
    *,
    role: str | None = None,
) -> tuple[ContentPart, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (TextPart(value),)
    if not isinstance(value, list):
        raise UnsupportedFeatureError(field, "must be a string or content block list")
    result: list[ContentPart] = []
    for index, raw_part in enumerate(value):
        part = require_object(raw_part, f"{field}[{index}]")
        part_type = part.get("type")
        if part_type == "text" and isinstance(part.get("text"), str):
            result.append(
                TextPart(
                    part["text"],
                    metadata=vendor_metadata(
                        Protocol.CLAUDE,
                        part,
                        {"type", "text"},
                    ),
                )
            )
        elif part_type == "image":
            if role == "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Claude image input blocks are only valid on user messages",
                )
            source = require_object(part.get("source"), f"{field}[{index}].source")
            metadata = vendor_metadata(
                Protocol.CLAUDE,
                part,
                {"type", "source"},
            )
            add_vendor_scope(
                metadata,
                Protocol.CLAUDE,
                "__source__",
                {
                    key: item
                    for key, item in source.items()
                    if key not in {"type", "media_type", "data", "url"}
                },
            )
            if source.get("type") == "base64":
                media_type = image_media_type(
                    source.get("media_type"),
                    f"{field}[{index}].source.media_type",
                )
                data = source.get("data")
                if not isinstance(data, str):
                    raise UnsupportedFeatureError(
                        f"{field}[{index}].source", "invalid base64 image"
                    )
                result.append(
                    ImagePart(
                        media_type=media_type,
                        data=data,
                        metadata=metadata,
                    )
                )
            elif source.get("type") == "url" and isinstance(source.get("url"), str):
                result.append(
                    ImagePart(
                        media_type=image_media_type_from_url(source["url"]),
                        url=source["url"],
                        metadata=metadata,
                    )
                )
            else:
                raise UnsupportedFeatureError(
                    f"{field}[{index}].source.type", "unsupported image source"
                )
        elif part_type == "tool_use":
            if role != "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Claude tool_use blocks are only valid on assistant messages",
                )
            name = part.get("name")
            if not isinstance(name, str):
                raise UnsupportedFeatureError(f"{field}[{index}].name", "must be a string")
            call_id = part.get("id")
            result.append(
                ToolCallPart(
                    id=call_id if isinstance(call_id, str) else None,
                    name=name,
                    arguments=require_object(part.get("input", {}), f"{field}[{index}].input"),
                    metadata=vendor_metadata(
                        Protocol.CLAUDE,
                        part,
                        {"type", "id", "name", "input"},
                    ),
                )
            )
        elif part_type == "tool_result":
            if role != "user":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Claude tool_result blocks are only valid on user messages",
                )
            call_id = part.get("tool_use_id")
            if not isinstance(call_id, str):
                raise UnsupportedFeatureError(f"{field}[{index}].tool_use_id", "must be a string")
            name = part.get("name")
            result.append(
                ToolResultPart(
                    tool_call_id=call_id,
                    name=name if isinstance(name, str) else None,
                    content=_decode_result_content(
                        part.get("content"), f"{field}[{index}].content"
                    ),
                    is_error=required_bool(part.get("is_error"), f"{field}[{index}].is_error"),
                    metadata=vendor_metadata(
                        Protocol.CLAUDE,
                        part,
                        {"type", "tool_use_id", "name", "content", "is_error"},
                    ),
                )
            )
        else:
            raise UnsupportedFeatureError(
                f"{field}[{index}].type", f"unsupported block {part_type!r}"
            )
    return tuple(result)


def _decode_result_content(value: Any, field: str) -> tuple[TextPart | ImagePart, ...]:
    if isinstance(value, Mapping):
        return (TextPart(orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode()),)
    content = _decode_content(value, field)
    if not all(isinstance(part, (TextPart, ImagePart)) for part in content):
        raise UnsupportedFeatureError(field, "nested tool blocks are not portable")
    return tuple(part for part in content if isinstance(part, (TextPart, ImagePart)))


def _encode_content(
    parts: Sequence[ContentPart],
    field: str = "content",
    *,
    role: str | None = None,
) -> str | list[dict[str, Any]]:
    if (
        len(parts) == 1
        and isinstance(parts[0], TextPart)
        and not native_extensions(Protocol.CLAUDE, parts[0].metadata)
    ):
        return parts[0].text
    result: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        if isinstance(part, TextPart):
            block = native_extensions(Protocol.CLAUDE, part.metadata)
            block.update({"type": "text", "text": part.text})
            result.append(block)
        elif isinstance(part, ImagePart):
            if role == "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Claude image input blocks are only valid on user messages",
                )
            if part.detail is not None:
                raise UnsupportedFeatureError(
                    f"{field}[{index}].detail",
                    "is not supported by Claude image blocks",
                )
            if part.data is not None:
                image_media_type(part.media_type, f"{field}[{index}].media_type")
            source = (
                {"type": "url", "url": part.url}
                if part.url is not None
                else {"type": "base64", "media_type": part.media_type, "data": part.data}
            )
            source.update(vendor_scope(Protocol.CLAUDE, part.metadata, "__source__"))
            block = native_extensions(Protocol.CLAUDE, part.metadata)
            block.update({"type": "image", "source": source})
            result.append(block)
        elif isinstance(part, ToolCallPart):
            if role != "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Claude tool calls are only valid on assistant messages",
                )
            if part.id is None:
                raise UnsupportedFeatureError(
                    f"{field}.content[{index}].id", "is required by Claude"
                )
            block = native_extensions(Protocol.CLAUDE, part.metadata)
            block.update(
                {
                    "type": "tool_use",
                    "id": part.id,
                    "name": part.name,
                    "input": thaw(part.arguments),
                }
            )
            result.append(block)
        elif isinstance(part, ToolResultPart):
            if role != "user":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Claude tool results are only valid on user messages",
                )
            if part.tool_call_id is None:
                raise UnsupportedFeatureError(
                    f"{field}.content[{index}].tool_call_id", "is required by Claude"
                )
            if not isinstance(part.is_error, bool):
                raise UnsupportedFeatureError(f"{field}[{index}].is_error", "must be a boolean")
            block = native_extensions(Protocol.CLAUDE, part.metadata)
            block.update(
                {
                    "type": "tool_result",
                    "tool_use_id": part.tool_call_id,
                    "content": _encode_content(part.content),
                }
            )
            _set_optional(block, "name", part.name)
            if part.is_error:
                block["is_error"] = True
            result.append(block)
    return result


def _decode_tools(value: Any) -> tuple[CanonicalTool, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UnsupportedFeatureError("tools", "must be a list")
    result: list[CanonicalTool] = []
    for index, raw_tool in enumerate(value):
        tool = require_object(raw_tool, f"tools[{index}]")
        name = tool.get("name")
        if not isinstance(name, str):
            raise UnsupportedFeatureError(f"tools[{index}].name", "must be a string")
        description = tool.get("description")
        result.append(
            CanonicalTool(
                name=name,
                description=description if isinstance(description, str) else None,
                input_schema=require_object(
                    tool.get("input_schema", {}), f"tools[{index}].input_schema"
                ),
                metadata=vendor_metadata(
                    Protocol.CLAUDE,
                    tool,
                    {"name", "description", "input_schema"},
                ),
            )
        )
    return tuple(result)


def _decode_tool_choice(value: Any) -> str | dict[str, Any] | None:
    if value is None:
        return None
    choice = require_object(value, "tool_choice")
    choice_type = choice.get("type")
    if choice_type == "auto":
        return "auto"
    if choice_type == "none":
        return "none"
    if choice_type == "any":
        return "required"
    if choice_type == "tool" and isinstance(choice.get("name"), str):
        return {"name": choice["name"]}
    raise UnsupportedFeatureError("tool_choice", f"unsupported choice {choice_type!r}")


def _encode_tool_choice(
    value: str | Mapping[str, Any], metadata: Mapping[str, Any]
) -> dict[str, Any]:
    choice = vendor_scope(Protocol.CLAUDE, metadata, "__tool_choice__")
    if isinstance(value, str):
        choices = {"auto": "auto", "none": "none", "required": "any"}
        if value not in choices:
            raise UnsupportedFeatureError("tool_choice", f"unsupported choice {value!r}")
        choice["type"] = choices[value]
        return choice
    if "names" in value:
        raise UnsupportedFeatureError(
            "tool_choice.names", "Claude cannot restrict tool choice to multiple names"
        )
    name = value.get("name")
    if not isinstance(name, str):
        raise UnsupportedFeatureError("tool_choice.name", "must be a string")
    choice.update({"type": "tool", "name": name})
    return choice


def _decode_usage(value: Any) -> CanonicalUsage | None:
    if value is None:
        return None
    usage = require_object(value, "usage")
    input_tokens = nonnegative_int(usage.get("input_tokens", 0), "usage.input_tokens")
    output_tokens = nonnegative_int(usage.get("output_tokens", 0), "usage.output_tokens")
    cache_read_tokens = nonnegative_int(
        usage.get("cache_read_input_tokens", 0),
        "usage.cache_read_input_tokens",
    )
    cache_write_tokens = nonnegative_int(
        usage.get("cache_creation_input_tokens", 0),
        "usage.cache_creation_input_tokens",
    )
    return CanonicalUsage(input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)


def _encode_usage(usage: CanonicalUsage) -> dict[str, int]:
    validate_usage(usage)
    encoded = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    if usage.cache_read_tokens or usage.cache_write_tokens:
        encoded.update(
            {
                "cache_read_input_tokens": usage.cache_read_tokens,
                "cache_creation_input_tokens": usage.cache_write_tokens,
            }
        )
    return encoded


def _decode_finish_reason(value: Any) -> FinishReason:
    return {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "pause_turn": "stop",
        "max_tokens": "length",
        "model_context_window_exceeded": "length",
        "tool_use": "tool_call",
        "refusal": "content_filter",
    }.get(value, "error")  # type: ignore[return-value]


def _encode_finish_reason(value: FinishReason) -> str:
    if value == "error":
        raise UnsupportedFeatureError(
            "finish_reason", "Claude has no successful stop reason for canonical errors"
        )
    return {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_call": "tool_use",
        "content_filter": "refusal",
    }[value]


def _encode_message(message: CanonicalMessage, index: int) -> dict[str, Any]:
    payload = native_extensions(Protocol.CLAUDE, message.metadata)
    payload.update(
        {
            "role": message.role,
            "content": _encode_content(
                message.content,
                f"messages[{index}].content",
                role=message.role,
            ),
        }
    )
    return payload


def _encode_tool(tool: CanonicalTool) -> dict[str, Any]:
    payload = native_extensions(Protocol.CLAUDE, tool.metadata)
    payload.update(
        {
            "name": tool.name,
            **({"description": tool.description} if tool.description is not None else {}),
            "input_schema": thaw(tool.input_schema),
        }
    )
    return payload


def _capture_tool_choice_extensions(metadata: dict[str, Any], value: Any) -> None:
    if not isinstance(value, Mapping):
        return
    add_vendor_scope(
        metadata,
        Protocol.CLAUDE,
        "__tool_choice__",
        {key: item for key, item in value.items() if key not in {"type", "name"}},
    )


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        payload[key] = value
