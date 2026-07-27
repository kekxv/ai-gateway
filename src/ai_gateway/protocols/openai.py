from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

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
    image_detail,
    image_media_type,
    image_media_type_from_url,
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
_RESPONSES_PORTABLE_FIELDS = {
    "model",
    "input",
    "instructions",
    "tools",
    "tool_choice",
    "temperature",
    "top_p",
    "max_output_tokens",
    "stream",
    "metadata",
    "parallel_tool_calls",
    "store",
    "background",
}
_RESPONSES_CANONICAL_FIELDS = {
    "model",
    "input",
    "instructions",
    "tools",
    "tool_choice",
    "temperature",
    "top_p",
    "max_output_tokens",
    "stream",
    "store",
    "background",
}


class OpenAIAdapter(ProtocolAdapter):
    protocol = Protocol.OPENAI

    def decode_request(self, payload: Mapping[str, Any]) -> CanonicalRequest:
        if "input" in payload and "messages" not in payload:
            return self.decode_responses_request(payload)

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
                parts = list(
                    _decode_content(
                        message.get("content"),
                        f"messages[{index}].content",
                        role=role,
                    )
                )
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

    def decode_responses_request(self, payload: Mapping[str, Any]) -> CanonicalRequest:
        _validate_responses_portable_fields(payload)
        model = payload.get("model")
        if not isinstance(model, str):
            raise UnsupportedFeatureError("model", "must be a string")
        system: list[ContentPart] = []
        system_messages: list[dict[str, Any]] = []
        instructions = payload.get("instructions")
        if instructions is not None:
            if not isinstance(instructions, str):
                raise UnsupportedFeatureError(
                    "instructions", "portable conversion requires a string"
                )
            system.append(TextPart(instructions))
            system_messages.append(
                {"role": "system", "part_count": 1, "extensions": {}}
            )
        messages, input_system, input_system_messages = _decode_responses_input(
            payload.get("input", "")
        )
        system.extend(input_system)
        system_messages.extend(input_system_messages)
        metadata = vendor_metadata(
            self.protocol,
            payload,
            _RESPONSES_CANONICAL_FIELDS,
        )
        if system_messages:
            add_vendor_scope(
                metadata,
                self.protocol,
                "__system_messages__",
                {"items": system_messages},
            )
        return CanonicalRequest(
            model=model,
            messages=messages,
            system=system,
            tools=_decode_responses_tools(payload.get("tools")),
            tool_choice=_decode_responses_tool_choice(payload.get("tool_choice")),
            temperature=optional_float(payload.get("temperature"), "temperature"),
            top_p=optional_float(payload.get("top_p"), "top_p"),
            max_output_tokens=optional_int(
                payload.get("max_output_tokens"), "max_output_tokens"
            ),
            stop_sequences=(),
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
        parts = list(
            _decode_content(
                message.get("content"),
                "choices[0].message.content",
                role="assistant",
            )
        )
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
            payload["usage"] = _encode_usage(response.usage)
        return payload

    def encode_responses_api_response(self, response: CanonicalResponse) -> dict[str, Any]:
        """Encode a canonical response in OpenAI Responses API format."""
        if response.message.role != "assistant":
            raise UnsupportedFeatureError("message.role", "must be assistant")

        # Generate response ID with "resp_" prefix
        response_id = response.metadata.get("response_id", f"resp_{uuid4().hex[:24]}")
        if not response_id.startswith("resp_"):
            response_id = f"resp_{response_id}"

        # Build output items
        output_items = []
        message_item = self._encode_responses_api_message_item(response.message)
        if message_item["content"]:
            output_items.append(message_item)

        # Handle tool calls as separate function_call items
        tool_calls = [part for part in response.message.content if isinstance(part, ToolCallPart)]
        for tool_call in tool_calls:
            call_id = tool_call.id or f"call_{uuid4().hex[:24]}"
            function_call_item = {
                "type": "function_call",
                "id": f"fc_{uuid4().hex[:24]}",
                "call_id": call_id,
                "name": tool_call.name,
                "arguments": orjson.dumps(thaw(tool_call.arguments)).decode(),
                "status": "completed",
            }
            output_items.append(function_call_item)

        # Build the response payload
        payload = {
            "id": response_id,
            "object": "response",
            "created_at": response.metadata.get("created", int(time.time())),
            "error": None,
            "incomplete_details": _responses_incomplete_details(response.finish_reason),
            "instructions": None,
            "max_output_tokens": None,
            "model": response.model,
            "output": output_items,
            "parallel_tool_calls": True,
            "previous_response_id": None,
            "reasoning": {"effort": None, "summary": None},
            "status": _map_finish_reason_to_status(response.finish_reason),
            "store": False,
            "temperature": 1.0,
            "text": {"format": {"type": "text"}},
            "tool_choice": "auto",
            "tools": [],
            "top_p": 1.0,
            "truncation": "disabled",
            "metadata": {},
        }

        # Add usage if present
        if response.usage is not None:
            payload["usage"] = _encode_responses_usage(response.usage)
        else:
            payload["usage"] = None

        return payload

    def _encode_responses_api_message_item(self, message: CanonicalMessage) -> dict[str, Any]:
        """Encode a canonical message as a Responses API message item."""
        content_parts = []
        for part in message.content:
            if isinstance(part, TextPart):
                content_parts.append({
                    "type": "output_text",
                    "text": part.text,
                    "annotations": [],
                })
            elif isinstance(part, ImagePart):
                raise UnsupportedFeatureError(
                    "message.content",
                    "image output cannot be represented as a Responses assistant message",
                )

        message_id = f"msg_{uuid4().hex[:24]}"
        return {
            "type": "message",
            "id": message_id,
            "role": message.role,
            "status": "completed",
            "content": content_parts,
        }

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
            choice["delta"] = delta_extensions
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
            payload["usage"] = _encode_usage(event.usage)
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


class _ResponsesAPIStreamEncoder(StreamEncoder):
    """Stateful encoder for official OpenAI Responses SSE event shapes."""

    def __init__(self) -> None:
        self._response_id = f"resp_{uuid4().hex[:24]}"
        self._message_id = f"msg_{uuid4().hex[:24]}"
        self._created_at = int(time.time())
        self._model = "unknown"
        self._sequence_number = 0
        self._started = False
        self._text_started = False
        self._text_done = False
        self._text = ""
        self._message_output_index: int | None = None
        self._tools: dict[tuple[int | None, str | None], dict[str, Any]] = {}
        self._output: list[dict[str, Any]] = []
        self._usage: CanonicalUsage | None = None
        self._finish_reason: FinishReason = "stop"

    def set_initial_usage(self, input_tokens: int) -> None:
        self._usage = CanonicalUsage(input_tokens, 0)

    def _frame(self, payload: dict[str, Any]) -> bytes:
        payload["sequence_number"] = self._sequence_number
        self._sequence_number += 1
        return encode_sse(payload, payload["type"])

    def _response(self, status: str) -> dict[str, Any]:
        return {
            "id": self._response_id,
            "object": "response",
            "created_at": self._created_at,
            "error": None,
            "incomplete_details": (
                _responses_incomplete_details(self._finish_reason)
                if status == "incomplete"
                else None
            ),
            "instructions": None,
            "max_output_tokens": None,
            "model": self._model,
            "output": [dict(item) for item in self._output],
            "parallel_tool_calls": True,
            "previous_response_id": None,
            "reasoning": {"effort": None, "summary": None},
            "status": status,
            "store": False,
            "temperature": 1.0,
            "text": {"format": {"type": "text"}},
            "tool_choice": "auto",
            "tools": [],
            "top_p": 1.0,
            "truncation": "disabled",
            "usage": _encode_responses_usage(self._usage) if self._usage is not None else None,
            "metadata": {},
        }

    def _ensure_started(self, model: str | None) -> list[bytes]:
        if model:
            self._model = model
        if self._started:
            return []
        self._started = True
        return [
            self._frame({"type": "response.created", "response": self._response("in_progress")}),
            self._frame(
                {"type": "response.in_progress", "response": self._response("in_progress")}
            ),
        ]

    def _start_text(self) -> list[bytes]:
        if self._text_started:
            return []
        self._text_started = True
        self._message_output_index = len(self._output)
        item = {
            "type": "message",
            "id": self._message_id,
            "role": "assistant",
            "status": "in_progress",
            "content": [],
        }
        self._output.append(item)
        return [
            self._frame(
                {
                    "type": "response.output_item.added",
                    "response_id": self._response_id,
                    "output_index": self._message_output_index,
                    "item": dict(item),
                }
            ),
            self._frame(
                {
                    "type": "response.content_part.added",
                    "response_id": self._response_id,
                    "item_id": self._message_id,
                    "output_index": self._message_output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                }
            ),
        ]

    def _finish_text(self) -> list[bytes]:
        if not self._text_started or self._text_done or self._message_output_index is None:
            return []
        self._text_done = True
        part = {"type": "output_text", "text": self._text, "annotations": []}
        item = {
            "type": "message",
            "id": self._message_id,
            "role": "assistant",
            "status": "completed",
            "content": [part],
        }
        self._output[self._message_output_index] = item
        common = {
            "response_id": self._response_id,
            "item_id": self._message_id,
            "output_index": self._message_output_index,
            "content_index": 0,
        }
        return [
            self._frame({"type": "response.output_text.done", **common, "text": self._text}),
            self._frame({"type": "response.content_part.done", **common, "part": part}),
            self._frame(
                {
                    "type": "response.output_item.done",
                    "response_id": self._response_id,
                    "output_index": self._message_output_index,
                    "item": item,
                }
            ),
        ]

    def _tool_state(self, event: StreamEvent) -> tuple[dict[str, Any], list[bytes]]:
        key = (event.tool_index, event.tool_call_id)
        state = self._tools.get(key)
        if state is not None:
            if event.tool_name:
                state["name"] = event.tool_name
            return state, []
        state = {
            "id": f"fc_{uuid4().hex[:24]}",
            "call_id": event.tool_call_id or f"call_{uuid4().hex[:24]}",
            "name": event.tool_name or "unknown",
            "arguments": "",
            "output_index": len(self._output),
            "done": False,
        }
        self._tools[key] = state
        item = {
            "type": "function_call",
            "id": state["id"],
            "call_id": state["call_id"],
            "name": state["name"],
            "arguments": "",
            "status": "in_progress",
        }
        self._output.append(item)
        return state, [
            self._frame(
                {
                    "type": "response.output_item.added",
                    "response_id": self._response_id,
                    "output_index": state["output_index"],
                    "item": item,
                }
            )
        ]

    def _finish_tools(self) -> list[bytes]:
        frames: list[bytes] = []
        for state in self._tools.values():
            if state["done"]:
                continue
            state["done"] = True
            item = {
                "type": "function_call",
                "id": state["id"],
                "call_id": state["call_id"],
                "name": state["name"],
                "arguments": state["arguments"],
                "status": "completed",
            }
            self._output[state["output_index"]] = item
            frames.append(
                self._frame(
                    {
                        "type": "response.function_call_arguments.done",
                        "response_id": self._response_id,
                        "item_id": state["id"],
                        "output_index": state["output_index"],
                        "arguments": state["arguments"],
                    }
                )
            )
            frames.append(
                self._frame(
                    {
                        "type": "response.output_item.done",
                        "response_id": self._response_id,
                        "output_index": state["output_index"],
                        "item": item,
                    }
                )
            )
        return frames

    def encode(self, event: StreamEvent) -> tuple[bytes, ...]:
        if event.type == "usage" and event.usage is not None:
            self._usage = event.usage
            return ()
        frames = self._ensure_started(event.model)
        if event.type in {"message_start", "content_start", "content_end", "heartbeat"}:
            return tuple(frames)
        if event.type == "content_delta" and event.text is not None:
            frames.extend(self._start_text())
            self._text += event.text
            frames.append(
                self._frame(
                    {
                        "type": "response.output_text.delta",
                        "response_id": self._response_id,
                        "item_id": self._message_id,
                        "output_index": self._message_output_index,
                        "content_index": 0,
                        "delta": event.text,
                    }
                )
            )
        elif event.type == "tool_call_delta":
            state, added = self._tool_state(event)
            frames.extend(added)
            if event.arguments_delta:
                state["arguments"] += event.arguments_delta
                frames.append(
                    self._frame(
                        {
                            "type": "response.function_call_arguments.delta",
                            "response_id": self._response_id,
                            "item_id": state["id"],
                            "output_index": state["output_index"],
                            "delta": event.arguments_delta,
                        }
                    )
                )
        elif event.type == "message_end":
            if event.finish_reason is not None:
                self._finish_reason = event.finish_reason
            frames.extend(self._finish_text())
            frames.extend(self._finish_tools())
        elif event.type == "done":
            frames.extend(self._finish_text())
            frames.extend(self._finish_tools())
            status = _map_finish_reason_to_status(self._finish_reason)
            terminal_type = {
                "completed": "response.completed",
                "incomplete": "response.incomplete",
                "failed": "response.failed",
            }[status]
            frames.append(self._frame({"type": terminal_type, "response": self._response(status)}))
        elif event.type == "error":
            response = self._response("failed")
            response["error"] = thaw(event.metadata)
            frames.append(self._frame({"type": "response.failed", "response": response}))
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
            if role == "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}]",
                    "image content is not valid on OpenAI assistant messages",
                )
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
                        media_type=image_media_type(
                            header[5:].split(";", 1)[0],
                            f"{field}[{index}].image_url.url",
                        ),
                        data=data,
                        detail=image_detail(
                            image.get("detail"),
                            f"{field}[{index}].image_url.detail",
                        ),
                        metadata=metadata,
                    )
                )
            else:
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
                        media_type=image_media_type_from_url(url),
                        url=url,
                        detail=image_detail(
                            image.get("detail"),
                            f"{field}[{index}].image_url.detail",
                        ),
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
    if not all(isinstance(part, TextPart) for part in parts):
        raise UnsupportedFeatureError(field, "OpenAI tool messages can contain only text")
    return cast(tuple[TextPart | ImagePart, ...], parts)


def _validate_responses_portable_fields(payload: Mapping[str, Any]) -> None:
    for field, value in payload.items():
        if field in _RESPONSES_PORTABLE_FIELDS:
            if field in {"store", "background"} and value not in {None, False}:
                raise UnsupportedFeatureError(field, "is not portable to this upstream")
            continue
        if value is not None:
            raise UnsupportedFeatureError(field, "is not portable to this upstream")


def _decode_responses_input(
    value: Any,
) -> tuple[
    tuple[CanonicalMessage, ...],
    tuple[ContentPart, ...],
    tuple[dict[str, Any], ...],
]:
    if isinstance(value, str):
        return (CanonicalMessage(role="user", content=(TextPart(value),)),), (), ()
    if not isinstance(value, list):
        raise UnsupportedFeatureError("input", "must be a string or list of input items")
    messages: list[CanonicalMessage] = []
    system: list[ContentPart] = []
    system_messages: list[dict[str, Any]] = []
    for index, raw_item in enumerate(value):
        item = require_object(raw_item, f"input[{index}]")
        item_type = item.get("type", "message")
        if item_type == "message":
            role = item.get("role")
            content = _decode_responses_content(item.get("content"), f"input[{index}].content")
            if role in {"system", "developer"}:
                if not all(isinstance(part, TextPart) for part in content):
                    raise UnsupportedFeatureError(
                        f"input[{index}].content", "system input supports text only"
                    )
                system.extend(content)
                system_messages.append(
                    {
                        "role": role,
                        "part_count": len(content),
                        "extensions": {},
                    }
                )
            elif role in {"user", "assistant"}:
                messages.append(CanonicalMessage(role=cast(Any, role), content=content))
            else:
                raise UnsupportedFeatureError(
                    f"input[{index}].role", f"unsupported role {role!r}"
                )
        elif item_type == "function_call":
            call_id = item.get("call_id", item.get("id"))
            name = item.get("name")
            if not isinstance(call_id, str):
                raise UnsupportedFeatureError(f"input[{index}].call_id", "must be a string")
            if not isinstance(name, str):
                raise UnsupportedFeatureError(f"input[{index}].name", "must be a string")
            messages.append(
                CanonicalMessage(
                    role="assistant",
                    content=(
                        ToolCallPart(
                            id=call_id,
                            name=name,
                            arguments=json_arguments(
                                item.get("arguments", "{}"), f"input[{index}].arguments"
                            ),
                        ),
                    ),
                )
            )
        elif item_type == "function_call_output":
            call_id = item.get("call_id")
            if not isinstance(call_id, str):
                raise UnsupportedFeatureError(f"input[{index}].call_id", "must be a string")
            messages.append(
                CanonicalMessage(
                    role="user",
                    content=(
                        ToolResultPart(
                            tool_call_id=call_id,
                            name=None,
                            content=_decode_responses_tool_output(
                                item.get("output", ""),
                                f"input[{index}].output",
                            ),
                        ),
                    ),
                )
            )
        else:
            raise UnsupportedFeatureError(
                f"input[{index}].type", f"unsupported item {item_type!r}"
            )
    return tuple(messages), tuple(system), tuple(system_messages)


def _decode_responses_content(value: Any, field: str) -> tuple[ContentPart, ...]:
    if isinstance(value, str):
        return (TextPart(value),)
    if not isinstance(value, list):
        raise UnsupportedFeatureError(field, "must be a string or content list")
    parts: list[ContentPart] = []
    for index, raw_part in enumerate(value):
        part = require_object(raw_part, f"{field}[{index}]")
        part_type = part.get("type")
        if part_type in {"input_text", "output_text"} and isinstance(part.get("text"), str):
            parts.append(TextPart(part["text"]))
        elif part_type == "input_image":
            image_url = part.get("image_url")
            if not isinstance(image_url, str):
                raise UnsupportedFeatureError(
                    f"{field}[{index}].image_url", "portable images require a URL"
                )
            detail = image_detail(part.get("detail"), f"{field}[{index}].detail")
            if image_url.startswith("data:"):
                header, separator, data = image_url.partition(",")
                if not separator or ";base64" not in header:
                    raise UnsupportedFeatureError(
                        f"{field}[{index}].image_url", "must be a base64 data URL"
                    )
                parts.append(
                    ImagePart(
                        media_type=image_media_type(
                            header[5:].split(";", 1)[0],
                            f"{field}[{index}].image_url",
                        ),
                        data=data,
                        detail=detail,
                    )
                )
            else:
                parts.append(
                    ImagePart(
                        media_type=image_media_type_from_url(image_url),
                        url=image_url,
                        detail=detail,
                    )
                )
        else:
            raise UnsupportedFeatureError(
                f"{field}[{index}].type", f"unsupported content {part_type!r}"
            )
    return tuple(parts)


def _decode_responses_tool_output(
    value: Any,
    field: str,
) -> tuple[TextPart | ImagePart, ...]:
    if isinstance(value, str):
        return (TextPart(value),)
    parts = _decode_responses_content(value, field)
    if not all(isinstance(part, (TextPart, ImagePart)) for part in parts):
        raise UnsupportedFeatureError(field, "contains a non-portable tool output")
    return cast(tuple[TextPart | ImagePart, ...], parts)


def _decode_responses_tools(value: Any) -> tuple[CanonicalTool, ...]:
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
        name = tool.get("name")
        if not isinstance(name, str):
            raise UnsupportedFeatureError(f"tools[{index}].name", "must be a string")
        metadata: dict[str, Any] = {}
        if "strict" in tool:
            add_vendor_scope(
                metadata,
                Protocol.OPENAI,
                "__function__",
                {"strict": tool["strict"]},
            )
        tools.append(
            CanonicalTool(
                name=name,
                description=(
                    tool["description"] if isinstance(tool.get("description"), str) else None
                ),
                input_schema=require_object(
                    tool.get("parameters", {}), f"tools[{index}].parameters"
                ),
                metadata=metadata,
            )
        )
    return tuple(tools)


def _decode_responses_tool_choice(value: Any) -> str | dict[str, Any] | None:
    if value is None or isinstance(value, str):
        return _decode_tool_choice(value)
    choice = require_object(value, "tool_choice")
    name = choice.get("name")
    if choice.get("type") != "function" or not isinstance(name, str):
        raise UnsupportedFeatureError("tool_choice", "unsupported portable tool selection")
    return {"name": name}


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
        if not all(isinstance(part, TextPart) for part in result.content):
            raise UnsupportedFeatureError(
                f"messages[{index}].content[0].content",
                "OpenAI tool messages can contain only text",
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
    if message.role == "assistant" and any(isinstance(part, ImagePart) for part in regular):
        raise UnsupportedFeatureError(
            f"messages[{index}].content",
            "image content is not valid on OpenAI assistant messages",
        )
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
            if part.data is not None:
                image_media_type(part.media_type, "content.image.media_type")
            image_detail(part.detail, "content.image.detail")
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
    total_input = nonnegative_int(usage.get("prompt_tokens", 0), "usage.prompt_tokens")
    output_tokens = nonnegative_int(usage.get("completion_tokens", 0), "usage.completion_tokens")
    details = require_object(usage.get("prompt_tokens_details", {}), "usage.prompt_tokens_details")
    cache_read = nonnegative_int(
        details.get("cached_tokens", 0),
        "usage.prompt_tokens_details.cached_tokens",
    )
    cache_write = nonnegative_int(
        details.get("cache_write_tokens", 0),
        "usage.prompt_tokens_details.cache_write_tokens",
    )
    input_tokens = total_input - cache_read - cache_write
    if input_tokens < 0:
        raise UnsupportedFeatureError(
            "usage.prompt_tokens",
            "cache token details exceed total input tokens",
        )
    return CanonicalUsage(input_tokens, output_tokens, cache_read, cache_write)


def _encode_usage(usage: CanonicalUsage) -> dict[str, Any]:
    validate_usage(usage)
    total_input = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    encoded: dict[str, Any] = {
        "prompt_tokens": total_input,
        "completion_tokens": usage.output_tokens,
        "total_tokens": total_input + usage.output_tokens,
    }
    if usage.cache_read_tokens or usage.cache_write_tokens:
        encoded["prompt_tokens_details"] = {
            "cached_tokens": usage.cache_read_tokens,
            "cache_write_tokens": usage.cache_write_tokens,
        }
    return encoded


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


def _map_finish_reason_to_status(finish_reason: FinishReason) -> str:
    """Map canonical finish reason to Responses API status."""
    return {
        "stop": "completed",
        "length": "incomplete",
        "tool_call": "completed",
        "content_filter": "incomplete",
        "error": "failed",
    }[finish_reason]


def _responses_incomplete_details(finish_reason: FinishReason) -> dict[str, str] | None:
    if finish_reason == "length":
        return {"reason": "max_output_tokens"}
    if finish_reason == "content_filter":
        return {"reason": "content_filter"}
    return None


def _encode_responses_usage(usage: CanonicalUsage) -> dict[str, Any]:
    validate_usage(usage)
    total_input = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    input_details = {"cached_tokens": usage.cache_read_tokens}
    if usage.cache_write_tokens:
        input_details["cache_write_tokens"] = usage.cache_write_tokens
    return {
        "input_tokens": total_input,
        "input_tokens_details": input_details,
        "output_tokens": usage.output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": total_input + usage.output_tokens,
    }


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
