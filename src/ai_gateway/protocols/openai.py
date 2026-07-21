from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

import orjson

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import (
    NO_STREAM_OUTPUT,
    ProtocolAdapter,
    StreamDecoder,
    StreamEncoder,
    UnsupportedFeatureError,
    add_vendor_scope,
    decode_sse,
    encode_sse,
    json_arguments,
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
    "messages",
    "tools",
    "tool_choice",
    "temperature",
    "top_p",
    "max_completion_tokens",
    "max_tokens",
    "stop",
    "stream",
}
_RESPONSE_FIELDS = {"id", "object", "created", "model", "choices", "usage"}


class OpenAIAdapter(ProtocolAdapter):
    protocol = Protocol.OPENAI

    def decode_request(self, payload: Mapping[str, Any]) -> CanonicalRequest:
        model = payload.get("model")
        if not isinstance(model, str):
            raise UnsupportedFeatureError("model", "must be a string")
        system: list[ContentPart] = []
        system_messages: list[dict[str, Any]] = []
        messages: list[CanonicalMessage] = []
        native_messages = payload.get("messages", [])
        if not isinstance(native_messages, list):
            raise UnsupportedFeatureError("messages", "must be a list")
        for index, value in enumerate(native_messages):
            message = require_object(value, f"messages[{index}]")
            role = message.get("role")
            if role in {"system", "developer"}:
                if "tool_calls" in message:
                    raise UnsupportedFeatureError(
                        f"messages[{index}].tool_calls",
                        "tool calls are only valid on assistant messages",
                    )
                system_parts = _decode_content(message.get("content"), f"messages[{index}].content")
                if not all(isinstance(part, TextPart) for part in system_parts):
                    raise UnsupportedFeatureError(
                        f"messages[{index}].content",
                        "system content must contain only text",
                    )
                system.extend(system_parts)
                system_messages.append(
                    {
                        "role": role,
                        "part_count": len(system_parts),
                        "extensions": {
                            key: thaw(item)
                            for key, item in message.items()
                            if key not in {"role", "content"}
                        },
                    }
                )
            elif role == "tool":
                if "tool_calls" in message:
                    raise UnsupportedFeatureError(
                        f"messages[{index}].tool_calls",
                        "tool calls are only valid on assistant messages",
                    )
                tool_call_id = message.get("tool_call_id")
                name = message.get("name")
                if not isinstance(tool_call_id, str):
                    raise UnsupportedFeatureError(
                        f"messages[{index}].tool_call_id", "must be a string"
                    )
                messages.append(
                    CanonicalMessage(
                        role="user",
                        content=(
                            ToolResultPart(
                                tool_call_id=tool_call_id,
                                name=name if isinstance(name, str) else None,
                                content=_decode_result_content(
                                    message.get("content"), f"messages[{index}].content"
                                ),
                            ),
                        ),
                        metadata=vendor_metadata(
                            self.protocol,
                            message,
                            {"role", "tool_call_id", "name", "content"},
                        ),
                    )
                )
            elif role in {"user", "assistant"}:
                parts = list(_decode_content(message.get("content"), f"messages[{index}].content"))
                if role == "user" and "tool_calls" in message:
                    raise UnsupportedFeatureError(
                        f"messages[{index}].tool_calls",
                        "tool calls are only valid on assistant messages",
                    )
                if role == "assistant":
                    parts.extend(
                        _decode_tool_calls(
                            message.get("tool_calls"), f"messages[{index}].tool_calls"
                        )
                    )
                messages.append(
                    CanonicalMessage(
                        role=cast(Any, role),
                        content=parts,
                        metadata=vendor_metadata(
                            self.protocol,
                            message,
                            {"role", "content", "tool_calls"},
                        ),
                    )
                )
            else:
                raise UnsupportedFeatureError(
                    f"messages[{index}].role", f"unsupported role {role!r}"
                )
        metadata = vendor_metadata(self.protocol, payload, _REQUEST_FIELDS)
        if system_messages:
            add_vendor_scope(
                metadata,
                self.protocol,
                "__system_messages__",
                {"items": system_messages},
            )
        _capture_tool_choice_extensions(metadata, payload.get("tool_choice"))
        return CanonicalRequest(
            model=model,
            messages=messages,
            system=system,
            tools=_decode_tools(payload.get("tools")),
            tool_choice=_decode_tool_choice(payload.get("tool_choice")),
            temperature=optional_float(payload.get("temperature"), "temperature"),
            top_p=optional_float(payload.get("top_p"), "top_p"),
            max_output_tokens=optional_int(
                payload.get("max_completion_tokens", payload.get("max_tokens")),
                "max_completion_tokens",
            ),
            stop_sequences=string_list(payload.get("stop"), "stop"),
            stream=required_bool(payload.get("stream"), "stream"),
            metadata=metadata,
        )

    def encode_request(self, request: CanonicalRequest) -> dict[str, Any]:
        payload = native_extensions(self.protocol, request.metadata)
        payload["model"] = request.model
        messages: list[dict[str, Any]] = []
        if request.system:
            if not all(isinstance(part, TextPart) for part in request.system):
                raise UnsupportedFeatureError("system", "must contain only text")
            scope = vendor_scope(self.protocol, request.metadata, "__system_messages__")
            descriptors = scope.get("items")
            consumed = 0
            if isinstance(descriptors, list):
                for descriptor in descriptors:
                    if not isinstance(descriptor, Mapping):
                        continue
                    count = descriptor.get("part_count")
                    role = descriptor.get("role")
                    if not isinstance(count, int) or role not in {"system", "developer"}:
                        continue
                    encoded_message = (
                        thaw(descriptor.get("extensions"))
                        if isinstance(descriptor.get("extensions"), Mapping)
                        else {}
                    )
                    encoded_message.update(
                        {
                            "role": role,
                            "content": _encode_content(request.system[consumed : consumed + count]),
                        }
                    )
                    messages.append(encoded_message)
                    consumed += count
            if consumed != len(request.system):
                messages = [{"role": "system", "content": _encode_content(request.system)}]
        messages.extend(
            _encode_message(message, index) for index, message in enumerate(request.messages)
        )
        payload["messages"] = messages
        if request.tools:
            payload["tools"] = [_encode_tool(tool) for tool in request.tools]
        if request.tool_choice is not None:
            payload["tool_choice"] = _encode_tool_choice(request.tool_choice, request.metadata)
        _set_optional(payload, "temperature", request.temperature)
        _set_optional(payload, "top_p", request.top_p)
        _set_optional(payload, "max_completion_tokens", request.max_output_tokens)
        if request.stop_sequences:
            payload["stop"] = list(request.stop_sequences)
        payload["stream"] = request.stream
        return payload

    def decode_response(self, payload: Mapping[str, Any]) -> CanonicalResponse:
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise UnsupportedFeatureError("choices", "must contain exactly one choice")
        choice = require_object(choices[0], "choices[0]")
        message = require_object(choice.get("message"), "choices[0].message")
        if message.get("role") != "assistant":
            raise UnsupportedFeatureError("choices[0].message.role", "must be assistant")
        parts = list(_decode_content(message.get("content"), "choices[0].message.content"))
        parts.extend(_decode_tool_calls(message.get("tool_calls"), "choices[0].message.tool_calls"))
        usage = _decode_usage(payload.get("usage"))
        model = payload.get("model")
        message_metadata = vendor_metadata(
            self.protocol,
            message,
            {"role", "content", "tool_calls"},
        )
        metadata = vendor_metadata(
            self.protocol,
            payload,
            _RESPONSE_FIELDS,
            response_id=payload.get("id"),
            created=payload.get("created"),
        )
        add_vendor_scope(
            metadata,
            self.protocol,
            "__choice__",
            {
                key: item
                for key, item in choice.items()
                if key not in {"index", "message", "finish_reason"}
            },
        )
        return CanonicalResponse(
            model=model if isinstance(model, str) else "",
            message=CanonicalMessage(role="assistant", content=parts, metadata=message_metadata),
            finish_reason=_decode_finish_reason(choice.get("finish_reason")),
            usage=usage,
            metadata=metadata,
        )

    def encode_response(self, response: CanonicalResponse) -> dict[str, Any]:
        if response.message.role != "assistant":
            raise UnsupportedFeatureError("message.role", "must be assistant")
        payload = native_extensions(self.protocol, response.metadata)
        encoded_message = _encode_message(response.message, 0)
        choice = vendor_scope(self.protocol, response.metadata, "__choice__")
        choice.update(
            {
                "index": 0,
                "message": encoded_message,
                "finish_reason": _encode_finish_reason(response.finish_reason),
            }
        )
        payload.update(
            {
                "id": response.metadata.get("response_id", "chatcmpl_gateway"),
                "object": "chat.completion",
                "model": response.model,
                "choices": [choice],
            }
        )
        if "created" in response.metadata:
            payload["created"] = response.metadata["created"]
        if response.usage is not None:
            validate_usage(response.usage)
            payload["usage"] = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
        return payload

    def create_stream_decoder(self) -> StreamDecoder:
        return _OpenAIStreamDecoder()

    def create_stream_encoder(self) -> StreamEncoder:
        return _OpenAIStreamEncoder(self)

    def decode_stream_event(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        return self.create_stream_decoder().decode(event)

    def _decode_isolated_stream_event(
        self, event: bytes | Mapping[str, Any]
    ) -> tuple[StreamEvent, ...]:
        _, payload = decode_sse(event)
        if payload == "[DONE]":
            return (StreamEvent(type="done"),)
        body = require_object(payload, "stream_event.data")
        if "error" in body:
            return (
                StreamEvent(
                    type="error",
                    metadata=require_object(body["error"], "stream_event.error"),
                ),
            )
        choices = body.get("choices", [])
        usage = _decode_usage(body.get("usage"))
        model = body.get("model") if isinstance(body.get("model"), str) else None
        if not isinstance(choices, list) or len(choices) > 1:
            raise UnsupportedFeatureError("stream_event.choices", "must contain at most one choice")
        events: list[StreamEvent] = []
        if not choices:
            if usage is not None:
                return (StreamEvent(type="usage", usage=usage, model=model),)
            raise UnsupportedFeatureError("stream_event.choices", "must contain a choice or usage")
        choice = require_object(choices[0], "stream_event.choices[0]")
        index = choice.get("index", 0)
        index = index if isinstance(index, int) else 0
        delta = require_object(choice.get("delta", {}), "stream_event.choices[0].delta")
        event_metadata = vendor_metadata(
            self.protocol,
            body,
            {"id", "object", "created", "model", "choices", "usage", "system_fingerprint"},
        )
        add_vendor_scope(
            event_metadata,
            self.protocol,
            "__choice__",
            {
                key: item
                for key, item in choice.items()
                if key not in {"index", "delta", "finish_reason"}
            },
        )
        add_vendor_scope(
            event_metadata,
            self.protocol,
            "__delta__",
            {
                key: item
                for key, item in delta.items()
                if key not in {"role", "content", "tool_calls"}
            },
        )
        finish = choice.get("finish_reason")
        role = delta.get("role")
        if role == "assistant":
            events.append(
                StreamEvent(
                    type="message_start",
                    index=index,
                    role="assistant",
                    model=model,
                    metadata=event_metadata,
                )
            )
        elif role is not None:
            raise UnsupportedFeatureError(
                "stream_event.choices[0].delta.role", f"unsupported role {role!r}"
            )
        content = delta.get("content")
        if isinstance(content, str):
            events.append(
                StreamEvent(
                    type="content_delta",
                    index=index,
                    text=content,
                    model=model,
                    metadata=event_metadata,
                )
            )
        elif content is not None:
            raise UnsupportedFeatureError(
                "stream_event.choices[0].delta.content", "must be a string or null"
            )
        tool_calls = delta.get("tool_calls")
        if tool_calls is not None and not isinstance(tool_calls, list):
            raise UnsupportedFeatureError(
                "stream_event.choices[0].delta.tool_calls", "must be a list"
            )
        for tool_index, raw_tool_call in enumerate(tool_calls or []):
            tool_call = require_object(
                raw_tool_call,
                f"stream_event.choices[0].delta.tool_calls[{tool_index}]",
            )
            function = require_object(
                tool_call.get("function", {}),
                f"stream_event.choices[0].delta.tool_calls[{tool_index}].function",
            )
            tool_metadata = thaw(event_metadata)
            add_vendor_scope(
                tool_metadata,
                self.protocol,
                "__stream_tool_call__",
                {
                    key: item
                    for key, item in tool_call.items()
                    if key not in {"index", "id", "type", "function"}
                },
            )
            add_vendor_scope(
                tool_metadata,
                self.protocol,
                "__stream_function__",
                {key: item for key, item in function.items() if key not in {"name", "arguments"}},
            )
            events.append(
                StreamEvent(
                    type="tool_call_delta",
                    index=index,
                    tool_index=nonnegative_int(
                        tool_call.get("index", tool_index),
                        f"stream_event.choices[0].delta.tool_calls[{tool_index}].index",
                    ),
                    tool_call_id=(
                        tool_call.get("id") if isinstance(tool_call.get("id"), str) else None
                    ),
                    tool_name=(
                        function.get("name") if isinstance(function.get("name"), str) else None
                    ),
                    arguments_delta=(
                        function.get("arguments")
                        if isinstance(function.get("arguments"), str)
                        else None
                    ),
                    model=model,
                    metadata=tool_metadata,
                )
            )
        if finish is not None:
            events.append(
                StreamEvent(
                    type="message_end",
                    index=index,
                    finish_reason=_decode_finish_reason(finish),
                    model=model,
                    metadata=event_metadata,
                )
            )
        if usage is not None:
            events.append(
                StreamEvent(type="usage", usage=usage, model=model, metadata=event_metadata)
            )
        if not events:
            raise UnsupportedFeatureError("stream_event", "contains no supported delta")
        return tuple(events)

    def encode_stream_event(self, event: StreamEvent) -> bytes:
        if event.type == "done":
            return encode_sse("[DONE]")
        if event.type in {"content_start", "content_end", "heartbeat"}:
            return NO_STREAM_OUTPUT
        choice = vendor_scope(self.protocol, event.metadata, "__choice__")
        choice.update({"index": 0, "delta": {}, "finish_reason": None})
        delta_extensions = vendor_scope(self.protocol, event.metadata, "__delta__")
        if event.type == "content_delta":
            delta_extensions["content"] = event.text or ""
            choice["delta"] = delta_extensions
        elif event.type == "tool_call_delta":
            function = vendor_scope(self.protocol, event.metadata, "__stream_function__")
            _set_optional(function, "name", event.tool_name)
            _set_optional(function, "arguments", event.arguments_delta)
            tool_call = vendor_scope(self.protocol, event.metadata, "__stream_tool_call__")
            tool_call.update(
                {
                    "index": event.tool_index if event.tool_index is not None else event.index,
                    "type": "function",
                    "function": function,
                }
            )
            _set_optional(tool_call, "id", event.tool_call_id)
            delta_extensions["tool_calls"] = [tool_call]
            choice["delta"] = delta_extensions
        elif event.type == "message_start":
            delta_extensions["role"] = event.role or "assistant"
            choice["delta"] = delta_extensions
        elif event.type == "message_end":
            if event.finish_reason is None:
                raise UnsupportedFeatureError("stream_event.finish_reason", "is required")
            choice["finish_reason"] = _encode_finish_reason(event.finish_reason)
        elif event.type == "usage":
            if event.usage is None:
                raise UnsupportedFeatureError("stream_event.usage", "is required")
            validate_usage(event.usage, "stream_event.usage")
            choice = {}
        elif event.type == "error":
            return encode_sse(
                {
                    "error": {
                        key: thaw(item)
                        for key, item in event.metadata.items()
                        if key != "vendor_extensions"
                    }
                }
            )
        else:
            raise UnsupportedFeatureError("stream_event.type", f"cannot encode {event.type!r}")
        payload = native_extensions(self.protocol, event.metadata)
        payload.update(
            {
                "object": "chat.completion.chunk",
                "model": event.model or "",
                "choices": [] if event.type == "usage" else [choice],
            }
        )
        if event.usage is not None:
            payload["usage"] = {
                "prompt_tokens": event.usage.input_tokens,
                "completion_tokens": event.usage.output_tokens,
                "total_tokens": event.usage.input_tokens + event.usage.output_tokens,
            }
        return encode_sse(payload)


class _OpenAIStreamDecoder(StreamDecoder):
    def __init__(self) -> None:
        self._adapter = OpenAIAdapter()
        self._message_started = False
        self._text_index: int | None = None
        self._tool_blocks: dict[int, int] = {}
        self._open_tools: set[int] = set()
        self._next_block_index = 0

    def _close_open_blocks(self, model: str | None = None) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        if self._text_index is not None:
            events.append(
                StreamEvent(
                    type="content_end",
                    index=self._text_index,
                    content_type="text",
                    model=model,
                )
            )
            self._text_index = None
        for tool_index in sorted(self._open_tools):
            events.append(
                StreamEvent(
                    type="content_end",
                    index=self._tool_blocks[tool_index],
                    tool_index=tool_index,
                    content_type="tool_call",
                    model=model,
                )
            )
        self._open_tools.clear()
        return events

    def decode(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        raw_events = self._adapter._decode_isolated_stream_event(event)
        events: list[StreamEvent] = []
        for raw in raw_events:
            if raw.type == "message_start":
                if not self._message_started:
                    events.append(raw)
                    self._message_started = True
            elif raw.type == "content_delta":
                if not self._message_started:
                    events.append(
                        StreamEvent(type="message_start", role="assistant", model=raw.model)
                    )
                    self._message_started = True
                if self._text_index is None:
                    self._text_index = self._next_block_index
                    self._next_block_index += 1
                    events.append(
                        StreamEvent(
                            type="content_start",
                            index=self._text_index,
                            content_type="text",
                            model=raw.model,
                        )
                    )
                events.append(replace(raw, index=self._text_index, content_type="text"))
            elif raw.type == "tool_call_delta":
                if self._text_index is not None:
                    events.extend(self._close_open_blocks(raw.model))
                tool_index = raw.tool_index if raw.tool_index is not None else 0
                block_index = self._tool_blocks.get(tool_index)
                if block_index is None:
                    block_index = self._next_block_index
                    self._next_block_index += 1
                    self._tool_blocks[tool_index] = block_index
                self._open_tools.add(tool_index)
                events.append(
                    replace(
                        raw,
                        index=block_index,
                        tool_index=tool_index,
                        content_type="tool_call",
                    )
                )
            elif raw.type == "message_end":
                events.extend(self._close_open_blocks(raw.model))
                events.append(raw)
            elif raw.type == "done":
                events.extend(self._close_open_blocks(raw.model))
                events.append(raw)
            else:
                events.append(raw)
        return tuple(events)


class _OpenAIStreamEncoder(StreamEncoder):
    def __init__(self, adapter: OpenAIAdapter) -> None:
        self._adapter = adapter
        self._tool_indices: dict[tuple[int, str | None], int] = {}
        self._next_tool_index = 0

    def encode(self, event: StreamEvent) -> tuple[bytes, ...]:
        if event.type in {"content_start", "content_end", "heartbeat"}:
            return ()
        if event.type == "message_start" and event.usage is not None:
            event = replace(event, usage=None)
        if event.type == "tool_call_delta":
            key = (event.index, event.tool_call_id)
            tool_index = event.tool_index
            if tool_index is None:
                tool_index = self._tool_indices.get(key)
                if tool_index is None:
                    tool_index = self._next_tool_index
                    self._next_tool_index += 1
                    self._tool_indices[key] = tool_index
            event = replace(event, tool_index=tool_index)
        frame = self._adapter.encode_stream_event(event)
        return (frame,) if frame else ()


def _decode_content(value: Any, field: str) -> tuple[ContentPart, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (TextPart(value),)
    if not isinstance(value, list):
        raise UnsupportedFeatureError(field, "must be a string or content block list")
    parts: list[ContentPart] = []
    for index, raw_part in enumerate(value):
        part = require_object(raw_part, f"{field}[{index}]")
        part_type = part.get("type")
        if part_type in {"text", "input_text", "output_text"} and isinstance(part.get("text"), str):
            parts.append(
                TextPart(
                    part["text"],
                    metadata=vendor_metadata(
                        Protocol.OPENAI,
                        part,
                        {"type", "text"},
                    ),
                )
            )
        elif part_type == "image_url":
            image = part.get("image_url")
            image = {"url": image} if isinstance(image, str) else require_object(image, field)
            url = image.get("url")
            if not isinstance(url, str):
                raise UnsupportedFeatureError(f"{field}[{index}].image_url.url", "must be a string")
            if url.startswith("data:"):
                header, separator, data = url.partition(",")
                if not separator or ";base64" not in header:
                    raise UnsupportedFeatureError(
                        f"{field}[{index}].image_url.url", "invalid data URI"
                    )
                metadata = vendor_metadata(
                    Protocol.OPENAI,
                    part,
                    {"type", "image_url"},
                )
                add_vendor_scope(
                    metadata,
                    Protocol.OPENAI,
                    "__image_url__",
                    {key: item for key, item in image.items() if key not in {"url", "detail"}},
                )
                parts.append(
                    ImagePart(
                        media_type=header[5:].split(";", 1)[0],
                        data=data,
                        metadata=metadata,
                    )
                )
            else:
                detail = image.get("detail")
                metadata = vendor_metadata(
                    Protocol.OPENAI,
                    part,
                    {"type", "image_url"},
                )
                add_vendor_scope(
                    metadata,
                    Protocol.OPENAI,
                    "__image_url__",
                    {key: item for key, item in image.items() if key not in {"url", "detail"}},
                )
                parts.append(
                    ImagePart(
                        url=url,
                        detail=detail if isinstance(detail, str) else None,
                        metadata=metadata,
                    )
                )
        else:
            raise UnsupportedFeatureError(
                f"{field}[{index}].type", f"unsupported block {part_type!r}"
            )
    return tuple(parts)


def _decode_result_content(value: Any, field: str) -> tuple[TextPart | ImagePart, ...]:
    parts = _decode_content(value, field)
    if not all(isinstance(part, (TextPart, ImagePart)) for part in parts):
        raise UnsupportedFeatureError(field, "tool results can contain only text or images")
    return cast(tuple[TextPart | ImagePart, ...], parts)


def _decode_tool_calls(value: Any, field: str) -> tuple[ToolCallPart, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UnsupportedFeatureError(field, "must be a list")
    result: list[ToolCallPart] = []
    for index, raw_call in enumerate(value):
        call = require_object(raw_call, f"{field}[{index}]")
        function = require_object(call.get("function"), f"{field}[{index}].function")
        name = function.get("name")
        if not isinstance(name, str):
            raise UnsupportedFeatureError(f"{field}[{index}].function.name", "must be a string")
        call_id = call.get("id")
        metadata = vendor_metadata(
            Protocol.OPENAI,
            call,
            {"id", "type", "function"},
        )
        add_vendor_scope(
            metadata,
            Protocol.OPENAI,
            "__function__",
            {key: item for key, item in function.items() if key not in {"name", "arguments"}},
        )
        result.append(
            ToolCallPart(
                id=call_id if isinstance(call_id, str) else None,
                name=name,
                arguments=json_arguments(
                    function.get("arguments", {}), f"{field}[{index}].function.arguments"
                ),
                metadata=metadata,
            )
        )
    return tuple(result)


def _decode_tools(value: Any) -> tuple[CanonicalTool, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UnsupportedFeatureError("tools", "must be a list")
    tools: list[CanonicalTool] = []
    for index, raw_tool in enumerate(value):
        tool = require_object(raw_tool, f"tools[{index}]")
        if tool.get("type") != "function":
            raise UnsupportedFeatureError(
                f"tools[{index}].type", "only function tools are portable"
            )
        function = require_object(tool.get("function"), f"tools[{index}].function")
        name = function.get("name")
        if not isinstance(name, str):
            raise UnsupportedFeatureError(f"tools[{index}].function.name", "must be a string")
        description = function.get("description")
        metadata = vendor_metadata(
            Protocol.OPENAI,
            tool,
            {"type", "function"},
        )
        add_vendor_scope(
            metadata,
            Protocol.OPENAI,
            "__function__",
            {
                key: item
                for key, item in function.items()
                if key not in {"name", "description", "parameters"}
            },
        )
        tools.append(
            CanonicalTool(
                name=name,
                description=description if isinstance(description, str) else None,
                input_schema=require_object(
                    function.get("parameters", {}), f"tools[{index}].function.parameters"
                ),
                metadata=metadata,
            )
        )
    return tuple(tools)


def _decode_tool_choice(value: Any) -> str | dict[str, Any] | None:
    if value is None:
        return value
    if isinstance(value, str):
        if value not in {"none", "auto", "required"}:
            raise UnsupportedFeatureError("tool_choice", f"unsupported choice {value!r}")
        return value
    choice = require_object(value, "tool_choice")
    function = require_object(choice.get("function"), "tool_choice.function")
    name = function.get("name")
    if choice.get("type") != "function" or not isinstance(name, str):
        raise UnsupportedFeatureError("tool_choice", "unsupported function selection")
    return {"name": name}


def _encode_tool_choice(value: str | Mapping[str, Any], metadata: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        if value not in {"none", "auto", "required"}:
            raise UnsupportedFeatureError("tool_choice", f"unsupported choice {value!r}")
        return value
    if "names" in value:
        raise UnsupportedFeatureError(
            "tool_choice.names", "OpenAI cannot restrict tool choice to multiple names"
        )
    name = value.get("name")
    if not isinstance(name, str):
        raise UnsupportedFeatureError("tool_choice.name", "must be a string")
    choice = vendor_scope(Protocol.OPENAI, metadata, "__tool_choice__")
    function = vendor_scope(Protocol.OPENAI, metadata, "__tool_choice_function__")
    function["name"] = name
    choice.update({"type": "function", "function": function})
    return choice


def _encode_message(message: CanonicalMessage, index: int) -> dict[str, Any]:
    results = [part for part in message.content if isinstance(part, ToolResultPart)]
    if results:
        if message.role != "user":
            raise UnsupportedFeatureError(
                f"messages[{index}].role",
                "tool results are only valid on canonical user messages",
            )
        if len(results) != 1 or len(message.content) != 1:
            raise UnsupportedFeatureError(
                f"messages[{index}].content",
                "OpenAI tool result messages cannot mix content blocks",
            )
        result = results[0]
        if not isinstance(result.is_error, bool):
            raise UnsupportedFeatureError(
                f"messages[{index}].content[0].is_error", "must be a boolean"
            )
        if result.is_error:
            raise UnsupportedFeatureError(
                f"messages[{index}].content[0].is_error",
                "OpenAI tool messages cannot represent an error flag",
            )
        if result.tool_call_id is None:
            raise UnsupportedFeatureError(
                f"messages[{index}].content[0].tool_call_id", "is required by OpenAI"
            )
        payload: dict[str, Any] = native_extensions(Protocol.OPENAI, message.metadata)
        payload.update(
            {
                "role": "tool",
                "tool_call_id": result.tool_call_id,
                "content": _encode_content(result.content),
            }
        )
        _set_optional(payload, "name", result.name)
        return payload
    calls = [part for part in message.content if isinstance(part, ToolCallPart)]
    if calls and message.role != "assistant":
        raise UnsupportedFeatureError(
            f"messages[{index}].role",
            "tool calls are only valid on canonical assistant messages",
        )
    regular = [part for part in message.content if not isinstance(part, ToolCallPart)]
    payload = native_extensions(Protocol.OPENAI, message.metadata)
    payload.update({"role": message.role, "content": _encode_content(regular) if regular else None})
    if calls:
        encoded_calls = []
        for part_index, call in enumerate(calls):
            if call.id is None:
                raise UnsupportedFeatureError(
                    f"messages[{index}].content[{part_index}].id", "is required by OpenAI"
                )
            function = vendor_scope(Protocol.OPENAI, call.metadata, "__function__")
            function.update(
                {
                    "name": call.name,
                    "arguments": orjson.dumps(thaw(call.arguments)).decode(),
                }
            )
            encoded_call = native_extensions(Protocol.OPENAI, call.metadata)
            encoded_call.update(
                {
                    "id": call.id,
                    "type": "function",
                    "function": function,
                }
            )
            encoded_calls.append(encoded_call)
        payload["tool_calls"] = encoded_calls
    return payload


def _encode_content(parts: Sequence[ContentPart]) -> str | list[dict[str, Any]]:
    if (
        len(parts) == 1
        and isinstance(parts[0], TextPart)
        and not native_extensions(Protocol.OPENAI, parts[0].metadata)
    ):
        return parts[0].text
    encoded: list[dict[str, Any]] = []
    for part in parts:
        if isinstance(part, TextPart):
            block = native_extensions(Protocol.OPENAI, part.metadata)
            block.update({"type": "text", "text": part.text})
            encoded.append(block)
        elif isinstance(part, ImagePart):
            url = (
                part.url
                if part.url is not None
                else f"data:{part.media_type};base64,{part.data or ''}"
            )
            image = vendor_scope(Protocol.OPENAI, part.metadata, "__image_url__")
            image["url"] = url
            _set_optional(image, "detail", part.detail)
            block = native_extensions(Protocol.OPENAI, part.metadata)
            block.update({"type": "image_url", "image_url": image})
            encoded.append(block)
        else:
            raise UnsupportedFeatureError("content", f"cannot encode {type(part).__name__} inline")
    return encoded


def _decode_usage(value: Any) -> CanonicalUsage | None:
    if value is None:
        return None
    usage = require_object(value, "usage")
    input_tokens = nonnegative_int(usage.get("prompt_tokens", 0), "usage.prompt_tokens")
    output_tokens = nonnegative_int(usage.get("completion_tokens", 0), "usage.completion_tokens")
    return CanonicalUsage(input_tokens=input_tokens, output_tokens=output_tokens)


def _decode_finish_reason(value: Any) -> FinishReason:
    return {
        "stop": "stop",
        "length": "length",
        "tool_calls": "tool_call",
        "function_call": "tool_call",
        "content_filter": "content_filter",
    }.get(value, "error")  # type: ignore[return-value]


def _encode_finish_reason(value: FinishReason) -> str:
    if value == "error":
        raise UnsupportedFeatureError(
            "finish_reason", "OpenAI has no successful finish reason for canonical errors"
        )
    return {
        "stop": "stop",
        "length": "length",
        "tool_call": "tool_calls",
        "content_filter": "content_filter",
    }[value]


def _encode_tool(tool: CanonicalTool) -> dict[str, Any]:
    payload = native_extensions(Protocol.OPENAI, tool.metadata)
    function = vendor_scope(Protocol.OPENAI, tool.metadata, "__function__")
    function.update(
        {
            "name": tool.name,
            **({"description": tool.description} if tool.description is not None else {}),
            "parameters": thaw(tool.input_schema),
        }
    )
    payload.update({"type": "function", "function": function})
    return payload


def _capture_tool_choice_extensions(metadata: dict[str, Any], value: Any) -> None:
    if not isinstance(value, Mapping):
        return
    add_vendor_scope(
        metadata,
        Protocol.OPENAI,
        "__tool_choice__",
        {key: item for key, item in value.items() if key not in {"type", "function"}},
    )
    function = value.get("function")
    if isinstance(function, Mapping):
        add_vendor_scope(
            metadata,
            Protocol.OPENAI,
            "__tool_choice_function__",
            {key: item for key, item in function.items() if key != "name"},
        )


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        payload[key] = value
