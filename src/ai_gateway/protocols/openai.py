from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import orjson

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import (
    ProtocolAdapter,
    UnsupportedFeatureError,
    decode_sse,
    encode_sse,
    json_arguments,
    native_extensions,
    optional_float,
    optional_int,
    require_object,
    string_list,
    thaw,
    vendor_metadata,
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
        messages: list[CanonicalMessage] = []
        native_messages = payload.get("messages", [])
        if not isinstance(native_messages, list):
            raise UnsupportedFeatureError("messages", "must be a list")
        for index, value in enumerate(native_messages):
            message = require_object(value, f"messages[{index}]")
            role = message.get("role")
            if role in {"system", "developer"}:
                system.extend(_decode_content(message.get("content"), f"messages[{index}].content"))
            elif role == "tool":
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
                    )
                )
            elif role in {"user", "assistant"}:
                parts = list(_decode_content(message.get("content"), f"messages[{index}].content"))
                if role == "assistant":
                    parts.extend(
                        _decode_tool_calls(
                            message.get("tool_calls"), f"messages[{index}].tool_calls"
                        )
                    )
                messages.append(CanonicalMessage(role=cast(Any, role), content=parts))
            else:
                raise UnsupportedFeatureError(
                    f"messages[{index}].role", f"unsupported role {role!r}"
                )
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
            stream=bool(payload.get("stream", False)),
            metadata=vendor_metadata(self.protocol, payload, _REQUEST_FIELDS),
        )

    def encode_request(self, request: CanonicalRequest) -> dict[str, Any]:
        payload = native_extensions(self.protocol, request.metadata)
        payload["model"] = request.model
        messages: list[dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": _encode_content(request.system)})
        messages.extend(
            _encode_message(message, index) for index, message in enumerate(request.messages)
        )
        payload["messages"] = messages
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        **(
                            {"description": tool.description}
                            if tool.description is not None
                            else {}
                        ),
                        "parameters": thaw(tool.input_schema),
                    },
                }
                for tool in request.tools
            ]
        if request.tool_choice is not None:
            payload["tool_choice"] = _encode_tool_choice(request.tool_choice)
        _set_optional(payload, "temperature", request.temperature)
        _set_optional(payload, "top_p", request.top_p)
        _set_optional(payload, "max_completion_tokens", request.max_output_tokens)
        if request.stop_sequences:
            payload["stop"] = list(request.stop_sequences)
        payload["stream"] = request.stream
        return payload

    def decode_response(self, payload: Mapping[str, Any]) -> CanonicalResponse:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise UnsupportedFeatureError("choices", "must contain at least one choice")
        choice = require_object(choices[0], "choices[0]")
        message = require_object(choice.get("message"), "choices[0].message")
        parts = list(_decode_content(message.get("content"), "choices[0].message.content"))
        parts.extend(_decode_tool_calls(message.get("tool_calls"), "choices[0].message.tool_calls"))
        usage = _decode_usage(payload.get("usage"))
        model = payload.get("model")
        return CanonicalResponse(
            model=model if isinstance(model, str) else "",
            message=CanonicalMessage(role="assistant", content=parts),
            finish_reason=_decode_finish_reason(choice.get("finish_reason")),
            usage=usage,
            metadata=vendor_metadata(
                self.protocol,
                payload,
                _RESPONSE_FIELDS,
                response_id=payload.get("id"),
                created=payload.get("created"),
            ),
        )

    def encode_response(self, response: CanonicalResponse) -> dict[str, Any]:
        payload = native_extensions(self.protocol, response.metadata)
        encoded_message = _encode_message(response.message, 0)
        payload.update(
            {
                "id": response.metadata.get("response_id", "chatcmpl_gateway"),
                "object": "chat.completion",
                "model": response.model,
                "choices": [
                    {
                        "index": 0,
                        "message": encoded_message,
                        "finish_reason": _encode_finish_reason(response.finish_reason),
                    }
                ],
            }
        )
        if "created" in response.metadata:
            payload["created"] = response.metadata["created"]
        if response.usage is not None:
            payload["usage"] = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
        return payload

    def decode_stream_event(self, event: bytes | Mapping[str, Any]) -> StreamEvent:
        _, payload = decode_sse(event)
        if payload == "[DONE]":
            return StreamEvent(type="done")
        body = require_object(payload, "stream_event.data")
        choices = body.get("choices", [])
        usage = _decode_usage(body.get("usage"))
        model = body.get("model") if isinstance(body.get("model"), str) else None
        if not isinstance(choices, list) or not choices:
            if usage is not None:
                return StreamEvent(type="usage", usage=usage, model=model)
            raise UnsupportedFeatureError("stream_event.choices", "must contain a choice")
        choice = require_object(choices[0], "stream_event.choices[0]")
        index = choice.get("index", 0)
        index = index if isinstance(index, int) else 0
        delta = require_object(choice.get("delta", {}), "stream_event.choices[0].delta")
        finish = choice.get("finish_reason")
        tool_calls = delta.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            tool_call = require_object(tool_calls[0], "stream_event.choices[0].delta.tool_calls[0]")
            function = require_object(tool_call.get("function", {}), "tool_call.function")
            return StreamEvent(
                type="tool_call_delta",
                index=index,
                tool_call_id=tool_call.get("id") if isinstance(tool_call.get("id"), str) else None,
                tool_name=function.get("name") if isinstance(function.get("name"), str) else None,
                arguments_delta=(
                    function.get("arguments")
                    if isinstance(function.get("arguments"), str)
                    else None
                ),
                model=model,
            )
        content = delta.get("content")
        if isinstance(content, str):
            return StreamEvent(type="content_delta", index=index, text=content, model=model)
        if finish is not None:
            return StreamEvent(
                type="message_end",
                index=index,
                finish_reason=_decode_finish_reason(finish),
                usage=usage,
                model=model,
            )
        role = delta.get("role")
        if role == "assistant":
            return StreamEvent(type="message_start", index=index, role="assistant", model=model)
        raise UnsupportedFeatureError("stream_event", "contains no supported delta")

    def encode_stream_event(self, event: StreamEvent) -> bytes:
        if event.type == "done":
            return encode_sse("[DONE]")
        choice: dict[str, Any] = {"index": event.index, "delta": {}, "finish_reason": None}
        if event.type == "content_delta":
            choice["delta"] = {"content": event.text or ""}
        elif event.type == "tool_call_delta":
            function: dict[str, Any] = {}
            _set_optional(function, "name", event.tool_name)
            _set_optional(function, "arguments", event.arguments_delta)
            tool_call: dict[str, Any] = {
                "index": event.index,
                "type": "function",
                "function": function,
            }
            _set_optional(tool_call, "id", event.tool_call_id)
            choice["delta"] = {"tool_calls": [tool_call]}
        elif event.type == "message_start":
            choice["delta"] = {"role": event.role or "assistant"}
        elif event.type == "message_end":
            choice["finish_reason"] = _encode_finish_reason(event.finish_reason or "stop")
        elif event.type == "usage":
            choice = {}
        elif event.type == "error":
            return encode_sse({"error": thaw(event.metadata)})
        else:
            raise UnsupportedFeatureError("stream_event.type", f"cannot encode {event.type!r}")
        payload: dict[str, Any] = {
            "object": "chat.completion.chunk",
            "model": event.model or "",
            "choices": [] if event.type == "usage" else [choice],
        }
        if event.usage is not None:
            payload["usage"] = {
                "prompt_tokens": event.usage.input_tokens,
                "completion_tokens": event.usage.output_tokens,
                "total_tokens": event.usage.input_tokens + event.usage.output_tokens,
            }
        return encode_sse(payload)


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
            parts.append(TextPart(part["text"]))
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
                parts.append(ImagePart(media_type=header[5:].split(";", 1)[0], data=data))
            else:
                detail = image.get("detail")
                parts.append(
                    ImagePart(
                        url=url,
                        detail=detail if isinstance(detail, str) else None,
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
        result.append(
            ToolCallPart(
                id=call_id if isinstance(call_id, str) else None,
                name=name,
                arguments=json_arguments(
                    function.get("arguments", {}), f"{field}[{index}].function.arguments"
                ),
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
        tools.append(
            CanonicalTool(
                name=name,
                description=description if isinstance(description, str) else None,
                input_schema=require_object(
                    function.get("parameters", {}), f"tools[{index}].function.parameters"
                ),
            )
        )
    return tuple(tools)


def _decode_tool_choice(value: Any) -> str | dict[str, Any] | None:
    if value is None or isinstance(value, str):
        return value
    choice = require_object(value, "tool_choice")
    function = require_object(choice.get("function"), "tool_choice.function")
    name = function.get("name")
    if choice.get("type") != "function" or not isinstance(name, str):
        raise UnsupportedFeatureError("tool_choice", "unsupported function selection")
    return {"name": name}


def _encode_tool_choice(value: str | Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        return value
    name = value.get("name")
    if not isinstance(name, str):
        raise UnsupportedFeatureError("tool_choice.name", "must be a string")
    return {"type": "function", "function": {"name": name}}


def _encode_message(message: CanonicalMessage, index: int) -> dict[str, Any]:
    results = [part for part in message.content if isinstance(part, ToolResultPart)]
    if results:
        if len(results) != 1 or len(message.content) != 1:
            raise UnsupportedFeatureError(
                f"messages[{index}].content",
                "OpenAI tool result messages cannot mix content blocks",
            )
        result = results[0]
        if result.tool_call_id is None:
            raise UnsupportedFeatureError(
                f"messages[{index}].content[0].tool_call_id", "is required by OpenAI"
            )
        payload: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": result.tool_call_id,
            "content": _encode_content(result.content),
        }
        _set_optional(payload, "name", result.name)
        return payload
    calls = [part for part in message.content if isinstance(part, ToolCallPart)]
    regular = [part for part in message.content if not isinstance(part, ToolCallPart)]
    payload = {"role": message.role, "content": _encode_content(regular) if regular else None}
    if calls:
        encoded_calls = []
        for part_index, call in enumerate(calls):
            if call.id is None:
                raise UnsupportedFeatureError(
                    f"messages[{index}].content[{part_index}].id", "is required by OpenAI"
                )
            encoded_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": orjson.dumps(thaw(call.arguments)).decode(),
                    },
                }
            )
        payload["tool_calls"] = encoded_calls
    return payload


def _encode_content(parts: Sequence[ContentPart]) -> str | list[dict[str, Any]]:
    if len(parts) == 1 and isinstance(parts[0], TextPart):
        return parts[0].text
    encoded: list[dict[str, Any]] = []
    for part in parts:
        if isinstance(part, TextPart):
            encoded.append({"type": "text", "text": part.text})
        elif isinstance(part, ImagePart):
            url = (
                part.url
                if part.url is not None
                else f"data:{part.media_type};base64,{part.data or ''}"
            )
            image: dict[str, Any] = {"url": url}
            _set_optional(image, "detail", part.detail)
            encoded.append({"type": "image_url", "image_url": image})
        else:
            raise UnsupportedFeatureError("content", f"cannot encode {type(part).__name__} inline")
    return encoded


def _decode_usage(value: Any) -> CanonicalUsage | None:
    if value is None:
        return None
    usage = require_object(value, "usage")
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise UnsupportedFeatureError("usage", "token counts must be integers")
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
    return {
        "stop": "stop",
        "length": "length",
        "tool_call": "tool_calls",
        "content_filter": "content_filter",
        "error": "stop",
    }[value]


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        payload[key] = value
