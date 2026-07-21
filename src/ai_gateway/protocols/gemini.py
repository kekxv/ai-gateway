from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import orjson

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import (
    ProtocolAdapter,
    UnsupportedFeatureError,
    decode_sse,
    encode_sse,
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
    "systemInstruction",
    "contents",
    "tools",
    "toolConfig",
    "generationConfig",
    "stream",
}
_RESPONSE_FIELDS = {"modelVersion", "responseId", "candidates", "usageMetadata"}


class GeminiAdapter(ProtocolAdapter):
    protocol = Protocol.GEMINI

    def decode_request(self, payload: Mapping[str, Any]) -> CanonicalRequest:
        model = payload.get("model")
        if not isinstance(model, str):
            raise UnsupportedFeatureError("model", "must be a string")
        contents = payload.get("contents", [])
        if not isinstance(contents, list):
            raise UnsupportedFeatureError("contents", "must be a list")
        messages: list[CanonicalMessage] = []
        for index, raw_content in enumerate(contents):
            content = require_object(raw_content, f"contents[{index}]")
            role = content.get("role", "user")
            canonical_role = "assistant" if role == "model" else role
            if canonical_role not in {"user", "assistant"}:
                raise UnsupportedFeatureError(
                    f"contents[{index}].role", f"unsupported role {role!r}"
                )
            messages.append(
                CanonicalMessage(
                    role=canonical_role,  # type: ignore[arg-type]
                    content=_decode_parts(content.get("parts"), f"contents[{index}].parts"),
                )
            )
        system: tuple[ContentPart, ...] = ()
        system_instruction = payload.get("systemInstruction")
        if system_instruction is not None:
            system_object = require_object(system_instruction, "systemInstruction")
            system = _decode_parts(system_object.get("parts"), "systemInstruction.parts")
        generation = require_object(payload.get("generationConfig", {}), "generationConfig")
        return CanonicalRequest(
            model=model,
            messages=messages,
            system=system,
            tools=_decode_tools(payload.get("tools")),
            tool_choice=_decode_tool_choice(payload.get("toolConfig")),
            temperature=optional_float(
                generation.get("temperature"), "generationConfig.temperature"
            ),
            top_p=optional_float(generation.get("topP"), "generationConfig.topP"),
            max_output_tokens=optional_int(
                generation.get("maxOutputTokens"), "generationConfig.maxOutputTokens"
            ),
            stop_sequences=string_list(
                generation.get("stopSequences"), "generationConfig.stopSequences"
            ),
            stream=bool(payload.get("stream", False)),
            metadata=vendor_metadata(self.protocol, payload, _REQUEST_FIELDS),
        )

    def encode_request(self, request: CanonicalRequest) -> dict[str, Any]:
        payload = native_extensions(self.protocol, request.metadata)
        payload["model"] = request.model
        if request.system:
            payload["systemInstruction"] = {"parts": _encode_parts(request.system, "system")}
        payload["contents"] = [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": _encode_parts(message.content, f"messages[{index}].content"),
            }
            for index, message in enumerate(request.messages)
        ]
        if request.tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            **(
                                {"description": tool.description}
                                if tool.description is not None
                                else {}
                            ),
                            "parameters": thaw(tool.input_schema),
                        }
                        for tool in request.tools
                    ]
                }
            ]
        if request.tool_choice is not None:
            payload["toolConfig"] = _encode_tool_choice(request.tool_choice)
        generation: dict[str, Any] = {}
        _set_optional(generation, "temperature", request.temperature)
        _set_optional(generation, "topP", request.top_p)
        _set_optional(generation, "maxOutputTokens", request.max_output_tokens)
        if request.stop_sequences:
            generation["stopSequences"] = list(request.stop_sequences)
        if generation:
            payload["generationConfig"] = generation
        payload["stream"] = request.stream
        return payload

    def decode_response(self, payload: Mapping[str, Any]) -> CanonicalResponse:
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise UnsupportedFeatureError("candidates", "must contain at least one candidate")
        candidate = require_object(candidates[0], "candidates[0]")
        content = require_object(candidate.get("content", {}), "candidates[0].content")
        parts = _decode_parts(content.get("parts"), "candidates[0].content.parts")
        finish_reason = _decode_finish_reason(candidate.get("finishReason"))
        if candidate.get("finishReason") == "STOP" and any(
            isinstance(part, ToolCallPart) for part in parts
        ):
            finish_reason = "tool_call"
        model = payload.get("modelVersion")
        return CanonicalResponse(
            model=model if isinstance(model, str) else "",
            message=CanonicalMessage(role="assistant", content=parts),
            finish_reason=finish_reason,
            usage=_decode_usage(payload.get("usageMetadata")),
            metadata=vendor_metadata(
                self.protocol,
                payload,
                _RESPONSE_FIELDS,
                response_id=payload.get("responseId"),
            ),
        )

    def encode_response(self, response: CanonicalResponse) -> dict[str, Any]:
        payload = native_extensions(self.protocol, response.metadata)
        payload.update(
            {
                "modelVersion": response.model,
                "responseId": response.metadata.get("response_id", "resp_gateway"),
                "candidates": [
                    {
                        "index": 0,
                        "content": {
                            "role": "model",
                            "parts": _encode_parts(response.message.content, "message.content"),
                        },
                        "finishReason": _encode_finish_reason(response.finish_reason),
                    }
                ],
            }
        )
        if response.usage is not None:
            payload["usageMetadata"] = _encode_usage(response.usage)
        return payload

    def decode_stream_event(self, event: bytes | Mapping[str, Any]) -> StreamEvent:
        _, raw_payload = decode_sse(event)
        payload = require_object(raw_payload, "stream_event.data")
        if "error" in payload:
            return StreamEvent(type="error", metadata=require_object(payload["error"], "error"))
        candidates = payload.get("candidates", [])
        usage = _decode_usage(payload.get("usageMetadata"))
        model = (
            payload.get("modelVersion") if isinstance(payload.get("modelVersion"), str) else None
        )
        if not isinstance(candidates, list) or not candidates:
            if usage is not None:
                return StreamEvent(type="usage", usage=usage, model=model)
            raise UnsupportedFeatureError("stream_event.candidates", "must contain a candidate")
        candidate = require_object(candidates[0], "stream_event.candidates[0]")
        index = candidate.get("index", 0)
        index = index if isinstance(index, int) else 0
        content = require_object(candidate.get("content", {}), "stream_event.candidate.content")
        parts = content.get("parts", [])
        if isinstance(parts, list) and parts:
            part = require_object(parts[0], "stream_event.candidate.content.parts[0]")
            if isinstance(part.get("text"), str):
                return StreamEvent(
                    type="content_delta", index=index, text=part["text"], model=model
                )
            if "functionCall" in part:
                call = require_object(part["functionCall"], "stream_event.functionCall")
                args = call.get("args", {})
                return StreamEvent(
                    type="tool_call_delta",
                    index=index,
                    tool_call_id=call.get("id") if isinstance(call.get("id"), str) else None,
                    tool_name=call.get("name") if isinstance(call.get("name"), str) else None,
                    arguments_delta=orjson.dumps(args).decode(),
                    model=model,
                )
        if candidate.get("finishReason") is not None:
            return StreamEvent(
                type="message_end",
                index=index,
                finish_reason=_decode_finish_reason(candidate.get("finishReason")),
                usage=usage,
                model=model,
            )
        raise UnsupportedFeatureError("stream_event", "contains no supported delta")

    def encode_stream_event(self, event: StreamEvent) -> bytes:
        if event.type == "error":
            return encode_sse({"error": thaw(event.metadata)})
        payload: dict[str, Any] = {}
        _set_optional(payload, "modelVersion", event.model)
        if event.type == "usage":
            payload["candidates"] = []
        else:
            candidate: dict[str, Any] = {"index": event.index}
            if event.type == "content_delta":
                candidate["content"] = {"role": "model", "parts": [{"text": event.text or ""}]}
            elif event.type == "tool_call_delta":
                try:
                    arguments = orjson.loads(event.arguments_delta or "{}")
                except orjson.JSONDecodeError as exc:
                    raise UnsupportedFeatureError(
                        "stream_event.arguments_delta", "Gemini requires complete JSON arguments"
                    ) from exc
                call: dict[str, Any] = {"name": event.tool_name or "", "args": arguments}
                _set_optional(call, "id", event.tool_call_id)
                candidate["content"] = {"role": "model", "parts": [{"functionCall": call}]}
            elif event.type in {"message_end", "done"}:
                candidate["finishReason"] = _encode_finish_reason(event.finish_reason or "stop")
            elif event.type == "message_start":
                candidate["content"] = {"role": "model", "parts": []}
            else:
                raise UnsupportedFeatureError("stream_event.type", f"cannot encode {event.type!r}")
            payload["candidates"] = [candidate]
        if event.usage is not None:
            payload["usageMetadata"] = _encode_usage(event.usage)
        return encode_sse(payload)


def _decode_parts(value: Any, field: str) -> tuple[ContentPart, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UnsupportedFeatureError(field, "must be a list")
    result: list[ContentPart] = []
    for index, raw_part in enumerate(value):
        part = require_object(raw_part, f"{field}[{index}]")
        if isinstance(part.get("text"), str):
            result.append(TextPart(part["text"]))
        elif "inlineData" in part or "inline_data" in part:
            data = require_object(
                part.get("inlineData", part.get("inline_data")), f"{field}[{index}].inlineData"
            )
            media_type = data.get("mimeType", data.get("mime_type"))
            encoded = data.get("data")
            if not isinstance(media_type, str) or not isinstance(encoded, str):
                raise UnsupportedFeatureError(f"{field}[{index}].inlineData", "invalid image")
            detail = part.get("detail")
            result.append(
                ImagePart(
                    media_type=media_type,
                    data=encoded,
                    detail=detail if isinstance(detail, str) else None,
                )
            )
        elif "fileData" in part or "file_data" in part:
            data = require_object(
                part.get("fileData", part.get("file_data")), f"{field}[{index}].fileData"
            )
            url = data.get("fileUri", data.get("file_uri"))
            if not isinstance(url, str):
                raise UnsupportedFeatureError(
                    f"{field}[{index}].fileData.fileUri", "must be a string"
                )
            detail = part.get("detail")
            result.append(
                ImagePart(
                    url=url,
                    detail=detail if isinstance(detail, str) else None,
                )
            )
        elif "functionCall" in part or "function_call" in part:
            call = require_object(
                part.get("functionCall", part.get("function_call")),
                f"{field}[{index}].functionCall",
            )
            name = call.get("name")
            if not isinstance(name, str):
                raise UnsupportedFeatureError(
                    f"{field}[{index}].functionCall.name", "must be a string"
                )
            call_id = call.get("id")
            result.append(
                ToolCallPart(
                    id=call_id if isinstance(call_id, str) else None,
                    name=name,
                    arguments=require_object(
                        call.get("args", {}), f"{field}[{index}].functionCall.args"
                    ),
                )
            )
        elif "functionResponse" in part or "function_response" in part:
            response = require_object(
                part.get("functionResponse", part.get("function_response")),
                f"{field}[{index}].functionResponse",
            )
            name = response.get("name")
            if not isinstance(name, str):
                raise UnsupportedFeatureError(
                    f"{field}[{index}].functionResponse.name", "must be a string"
                )
            response_value = response.get("response", {})
            response_object = require_object(
                response_value, f"{field}[{index}].functionResponse.response"
            )
            if set(response_object) == {"result"} and isinstance(response_object["result"], str):
                text = response_object["result"]
            else:
                text = orjson.dumps(response_object, option=orjson.OPT_SORT_KEYS).decode()
            response_id = response.get("id")
            result.append(
                ToolResultPart(
                    tool_call_id=response_id if isinstance(response_id, str) else None,
                    name=name,
                    content=(TextPart(text),),
                )
            )
        else:
            raise UnsupportedFeatureError(f"{field}[{index}]", "unsupported Gemini part")
    return tuple(result)


def _encode_parts(parts: Sequence[ContentPart], field: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        if isinstance(part, TextPart):
            result.append({"text": part.text})
        elif isinstance(part, ImagePart):
            block: dict[str, Any]
            if part.url is not None:
                block = {
                    "fileData": {
                        **({"mimeType": part.media_type} if part.media_type is not None else {}),
                        "fileUri": part.url,
                    }
                }
            else:
                block = {"inlineData": {"mimeType": part.media_type, "data": part.data}}
            _set_optional(block, "detail", part.detail)
            result.append(block)
        elif isinstance(part, ToolCallPart):
            call: dict[str, Any] = {"name": part.name, "args": thaw(part.arguments)}
            _set_optional(call, "id", part.id)
            result.append({"functionCall": call})
        elif isinstance(part, ToolResultPart):
            if part.name is None:
                raise UnsupportedFeatureError(f"{field}[{index}].name", "is required by Gemini")
            if len(part.content) != 1 or not isinstance(part.content[0], TextPart):
                raise UnsupportedFeatureError(
                    f"{field}[{index}].content", "Gemini function responses require one text value"
                )
            text = part.content[0].text
            try:
                response_value = orjson.loads(text)
            except orjson.JSONDecodeError:
                response_value = {"result": text}
            if not isinstance(response_value, dict):
                response_value = {"result": response_value}
            response: dict[str, Any] = {"name": part.name, "response": response_value}
            _set_optional(response, "id", part.tool_call_id)
            result.append({"functionResponse": response})
    return result


def _decode_tools(value: Any) -> tuple[CanonicalTool, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UnsupportedFeatureError("tools", "must be a list")
    result: list[CanonicalTool] = []
    for tool_index, raw_group in enumerate(value):
        group = require_object(raw_group, f"tools[{tool_index}]")
        declarations = group.get("functionDeclarations", group.get("function_declarations"))
        if declarations is None:
            raise UnsupportedFeatureError(
                f"tools[{tool_index}]", "only function declarations are portable"
            )
        if not isinstance(declarations, list):
            raise UnsupportedFeatureError(
                f"tools[{tool_index}].functionDeclarations", "must be a list"
            )
        for function_index, raw_declaration in enumerate(declarations):
            declaration = require_object(
                raw_declaration, f"tools[{tool_index}].functionDeclarations[{function_index}]"
            )
            name = declaration.get("name")
            if not isinstance(name, str):
                raise UnsupportedFeatureError("tools.functionDeclarations.name", "must be a string")
            description = declaration.get("description")
            result.append(
                CanonicalTool(
                    name=name,
                    description=description if isinstance(description, str) else None,
                    input_schema=require_object(
                        declaration.get("parameters", {}), "tools.functionDeclarations.parameters"
                    ),
                )
            )
    return tuple(result)


def _decode_tool_choice(value: Any) -> str | dict[str, Any] | None:
    if value is None:
        return None
    config = require_object(value, "toolConfig")
    calling = require_object(
        config.get("functionCallingConfig", config.get("function_calling_config", {})),
        "toolConfig.functionCallingConfig",
    )
    mode = calling.get("mode", "AUTO")
    names = calling.get("allowedFunctionNames", calling.get("allowed_function_names", []))
    if isinstance(names, list) and len(names) == 1 and isinstance(names[0], str):
        return {"name": names[0]}
    choices = {"AUTO": "auto", "NONE": "none", "ANY": "required"}
    if mode not in choices:
        raise UnsupportedFeatureError(
            "toolConfig.functionCallingConfig.mode", f"unsupported {mode!r}"
        )
    return choices[mode]


def _encode_tool_choice(value: str | Mapping[str, Any]) -> dict[str, Any]:
    config: dict[str, Any]
    if isinstance(value, str):
        modes = {"auto": "AUTO", "none": "NONE", "required": "ANY"}
        if value not in modes:
            raise UnsupportedFeatureError("tool_choice", f"unsupported choice {value!r}")
        config = {"mode": modes[value]}
    else:
        name = value.get("name")
        if not isinstance(name, str):
            raise UnsupportedFeatureError("tool_choice.name", "must be a string")
        config = {"mode": "ANY", "allowedFunctionNames": [name]}
    return {"functionCallingConfig": config}


def _decode_usage(value: Any) -> CanonicalUsage | None:
    if value is None:
        return None
    usage = require_object(value, "usageMetadata")
    input_tokens = usage.get("promptTokenCount", usage.get("prompt_token_count", 0))
    output_tokens = usage.get("candidatesTokenCount", usage.get("candidates_token_count", 0))
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise UnsupportedFeatureError("usageMetadata", "token counts must be integers")
    return CanonicalUsage(input_tokens=input_tokens, output_tokens=output_tokens)


def _encode_usage(usage: CanonicalUsage) -> dict[str, int]:
    return {
        "promptTokenCount": usage.input_tokens,
        "candidatesTokenCount": usage.output_tokens,
        "totalTokenCount": usage.input_tokens + usage.output_tokens,
    }


def _decode_finish_reason(value: Any) -> FinishReason:
    if value in {"STOP", "FINISH_REASON_UNSPECIFIED"}:
        return "stop"
    if value == "MAX_TOKENS":
        return "length"
    if value in {
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "IMAGE_SAFETY",
    }:
        return "content_filter"
    return "error"


def _encode_finish_reason(value: FinishReason) -> str:
    return {
        "stop": "STOP",
        "length": "MAX_TOKENS",
        "tool_call": "STOP",
        "content_filter": "SAFETY",
        "error": "OTHER",
    }[value]


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        payload[key] = value
