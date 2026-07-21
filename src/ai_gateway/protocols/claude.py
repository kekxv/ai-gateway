from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import orjson

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import (
    ProtocolAdapter,
    UnsupportedFeatureError,
    add_vendor_scope,
    decode_sse,
    encode_sse,
    native_extensions,
    optional_float,
    optional_int,
    require_object,
    required_bool,
    string_list,
    thaw,
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

    def decode_request(self, payload: Mapping[str, Any]) -> CanonicalRequest:
        model = payload.get("model")
        if not isinstance(model, str):
            raise UnsupportedFeatureError("model", "must be a string")
        messages_value = payload.get("messages", [])
        if not isinstance(messages_value, list):
            raise UnsupportedFeatureError("messages", "must be a list")
        messages: list[CanonicalMessage] = []
        for index, raw_message in enumerate(messages_value):
            message = require_object(raw_message, f"messages[{index}]")
            role = message.get("role")
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
            system=_decode_content(payload.get("system"), "system"),
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
        _set_optional(payload, "max_tokens", request.max_output_tokens)
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
            payload["usage"] = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        return payload

    def decode_stream_event(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        event_name, raw_payload = decode_sse(event)
        payload = require_object(raw_payload, "stream_event.data")
        event_type = payload.get("type", event_name)
        if event_type == "content_block_delta":
            delta = require_object(payload.get("delta"), "stream_event.delta")
            index = payload.get("index", 0)
            index = index if isinstance(index, int) else 0
            if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                return (StreamEvent(type="content_delta", index=index, text=delta["text"]),)
            if delta.get("type") == "input_json_delta":
                partial_json = delta.get("partial_json")
                return (
                    StreamEvent(
                        type="tool_call_delta",
                        index=index,
                        arguments_delta=(partial_json if isinstance(partial_json, str) else None),
                    ),
                )
            raise UnsupportedFeatureError(
                "stream_event.delta.type", f"unsupported delta {delta.get('type')!r}"
            )
        if event_type == "content_block_start":
            block = require_object(payload.get("content_block"), "stream_event.content_block")
            index = payload.get("index", 0)
            index = index if isinstance(index, int) else 0
            if block.get("type") == "tool_use":
                arguments = block.get("input", {})
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
                        arguments_delta=orjson.dumps(arguments).decode(),
                    ),
                )
            if block.get("type") == "text":
                text = block.get("text", "")
                if not isinstance(text, str):
                    raise UnsupportedFeatureError(
                        "stream_event.content_block.text", "must be a string"
                    )
                return (StreamEvent(type="content_delta", index=index, text=text),)
            raise UnsupportedFeatureError(
                "stream_event.content_block.type",
                f"unsupported block {block.get('type')!r}",
            )
        if event_type == "content_block_stop":
            index = payload.get("index", 0)
            return (StreamEvent(type="content_end", index=index if isinstance(index, int) else 0),)
        if event_type == "message_start":
            message = require_object(payload.get("message", {}), "stream_event.message")
            model = message.get("model") if isinstance(message.get("model"), str) else None
            events = [StreamEvent(type="message_start", role="assistant", model=model)]
            usage = _decode_usage(message.get("usage"))
            if usage is not None:
                events.append(StreamEvent(type="usage", usage=usage, model=model))
            return tuple(events)
        if event_type == "message_delta":
            delta = require_object(payload.get("delta", {}), "stream_event.delta")
            events = []
            stop_reason = delta.get("stop_reason")
            if stop_reason is not None:
                events.append(
                    StreamEvent(
                        type="message_end",
                        finish_reason=_decode_finish_reason(stop_reason),
                    )
                )
            usage = _decode_usage(payload.get("usage"))
            if usage is not None:
                events.append(StreamEvent(type="usage", usage=usage))
            if not events:
                raise UnsupportedFeatureError(
                    "stream_event", "message_delta contains neither stop reason nor usage"
                )
            return tuple(events)
        if event_type == "message_stop":
            return (StreamEvent(type="done"),)
        if event_type == "ping":
            return (StreamEvent(type="heartbeat"),)
        if event_type == "error":
            error = payload.get("error", payload)
            return (
                StreamEvent(
                    type="error",
                    metadata=require_object(error, "stream_event.error"),
                ),
            )
        raise UnsupportedFeatureError(
            "stream_event.type", f"unsupported Claude event {event_type!r}"
        )

    def encode_stream_event(self, event: StreamEvent) -> bytes:
        if event.type == "content_delta":
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
            if event.usage is None:
                raise UnsupportedFeatureError("stream_event.usage", "is required")
            payload = {
                "type": "message_delta",
                "delta": {},
                "usage": _encode_usage(event.usage),
            }
        else:
            raise UnsupportedFeatureError("stream_event.type", f"cannot encode {event.type!r}")
        return encode_sse(payload, str(payload["type"]))


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
            detail = part.get("detail")
            metadata = vendor_metadata(
                Protocol.CLAUDE,
                part,
                {"type", "source", "detail"},
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
                media_type = source.get("media_type")
                data = source.get("data")
                if not isinstance(media_type, str) or not isinstance(data, str):
                    raise UnsupportedFeatureError(
                        f"{field}[{index}].source", "invalid base64 image"
                    )
                result.append(
                    ImagePart(
                        media_type=media_type,
                        data=data,
                        detail=detail if isinstance(detail, str) else None,
                        metadata=metadata,
                    )
                )
            elif source.get("type") == "url" and isinstance(source.get("url"), str):
                result.append(
                    ImagePart(
                        url=source["url"],
                        detail=detail if isinstance(detail, str) else None,
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
            source = (
                {"type": "url", "url": part.url}
                if part.url is not None
                else {"type": "base64", "media_type": part.media_type, "data": part.data}
            )
            source.update(vendor_scope(Protocol.CLAUDE, part.metadata, "__source__"))
            block = native_extensions(Protocol.CLAUDE, part.metadata)
            block.update({"type": "image", "source": source})
            _set_optional(block, "detail", part.detail)
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
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise UnsupportedFeatureError("usage", "token counts must be integers")
    return CanonicalUsage(input_tokens=input_tokens, output_tokens=output_tokens)


def _encode_usage(usage: CanonicalUsage) -> dict[str, int]:
    return {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


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
