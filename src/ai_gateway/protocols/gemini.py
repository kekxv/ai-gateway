from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

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
                    content=_decode_parts(
                        content.get("parts"),
                        f"contents[{index}].parts",
                        role=canonical_role,
                    ),
                    metadata=vendor_metadata(
                        self.protocol,
                        content,
                        {"role", "parts"},
                    ),
                )
            )
        system: tuple[ContentPart, ...] = ()
        system_instruction = payload.get("systemInstruction")
        if system_instruction is not None:
            system_object = require_object(system_instruction, "systemInstruction")
            system = _decode_parts(system_object.get("parts"), "systemInstruction.parts")
            if not all(isinstance(part, TextPart) for part in system):
                raise UnsupportedFeatureError(
                    "systemInstruction.parts", "system content must contain only text"
                )
        generation = require_object(payload.get("generationConfig", {}), "generationConfig")
        metadata = vendor_metadata(self.protocol, payload, _REQUEST_FIELDS)
        if system_instruction is not None:
            add_vendor_scope(
                metadata,
                self.protocol,
                "__system_instruction__",
                {key: item for key, item in system_object.items() if key not in {"role", "parts"}},
            )
        _capture_config_extensions(
            metadata,
            payload.get("toolConfig"),
            generation,
        )
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
            stream=required_bool(payload.get("stream"), "stream"),
            metadata=metadata,
        )

    def encode_request(self, request: CanonicalRequest) -> dict[str, Any]:
        payload = native_extensions(self.protocol, request.metadata)
        payload["model"] = request.model
        if request.system:
            if not all(isinstance(part, TextPart) for part in request.system):
                raise UnsupportedFeatureError("system", "must contain only text")
            system_instruction = vendor_scope(
                self.protocol, request.metadata, "__system_instruction__"
            )
            system_instruction["parts"] = _encode_parts(request.system, "system")
            payload["systemInstruction"] = system_instruction
        payload["contents"] = [
            _encode_message(message, index) for index, message in enumerate(request.messages)
        ]
        if request.tools:
            payload["tools"] = [_encode_tool_group((tool,)) for tool in request.tools]
        if request.tool_choice is not None:
            payload["toolConfig"] = _encode_tool_choice(request.tool_choice, request.metadata)
        generation = vendor_scope(self.protocol, request.metadata, "__generation_config__")
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
        model = payload.get("modelVersion")
        metadata = vendor_metadata(
            self.protocol,
            payload,
            _RESPONSE_FIELDS,
            response_id=payload.get("responseId"),
        )
        if candidates in (None, []):
            prompt_feedback = require_object(payload.get("promptFeedback", {}), "promptFeedback")
            block_reason = prompt_feedback.get("blockReason")
            if not isinstance(block_reason, str) or block_reason in {
                "",
                "BLOCK_REASON_UNSPECIFIED",
            }:
                raise UnsupportedFeatureError(
                    "candidates", "must contain exactly one candidate or a blocked prompt"
                )
            return CanonicalResponse(
                model=model if isinstance(model, str) else "",
                message=CanonicalMessage(role="assistant", content=()),
                finish_reason="content_filter",
                usage=_decode_usage(payload.get("usageMetadata")),
                metadata=metadata,
            )
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise UnsupportedFeatureError("candidates", "must contain exactly one candidate")
        candidate = require_object(candidates[0], "candidates[0]")
        finish_reason = _decode_finish_reason(candidate.get("finishReason"))
        content = require_object(candidate.get("content", {}), "candidates[0].content")
        if content.get("role") != "model" and not (
            finish_reason == "content_filter" and content.get("role") is None
        ):
            raise UnsupportedFeatureError("candidates[0].content.role", "must be model")
        parts = _decode_parts(content.get("parts"), "candidates[0].content.parts", role="assistant")
        if candidate.get("finishReason") == "STOP" and any(
            isinstance(part, ToolCallPart) for part in parts
        ):
            finish_reason = "tool_call"
        add_vendor_scope(
            metadata,
            self.protocol,
            "__candidate__",
            {
                key: item
                for key, item in candidate.items()
                if key not in {"index", "content", "finishReason"}
            },
        )
        return CanonicalResponse(
            model=model if isinstance(model, str) else "",
            message=CanonicalMessage(
                role="assistant",
                content=parts,
                metadata=vendor_metadata(
                    self.protocol,
                    content,
                    {"role", "parts"},
                ),
            ),
            finish_reason=finish_reason,
            usage=_decode_usage(payload.get("usageMetadata")),
            metadata=metadata,
        )

    def encode_response(self, response: CanonicalResponse) -> dict[str, Any]:
        if response.message.role != "assistant":
            raise UnsupportedFeatureError("message.role", "must be assistant")
        payload = native_extensions(self.protocol, response.metadata)
        content = native_extensions(self.protocol, response.message.metadata)
        content.update(
            {
                "role": "model",
                "parts": _encode_parts(
                    response.message.content,
                    "message.content",
                    role="assistant",
                ),
            }
        )
        candidate = vendor_scope(self.protocol, response.metadata, "__candidate__")
        candidate.update(
            {
                "index": 0,
                "content": content,
                "finishReason": _encode_finish_reason(response.finish_reason),
            }
        )
        payload.update(
            {
                "modelVersion": response.model,
                "responseId": response.metadata.get("response_id", "resp_gateway"),
                "candidates": [candidate],
            }
        )
        if response.usage is not None:
            validate_usage(response.usage)
            payload["usageMetadata"] = _encode_usage(response.usage)
        return payload

    def create_stream_decoder(self) -> StreamDecoder:
        return _GeminiStreamDecoder()

    def create_stream_encoder(self) -> StreamEncoder:
        return _GeminiStreamEncoder(self)

    def decode_stream_event(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        return self.create_stream_decoder().decode(event)

    def _decode_isolated_stream_event(
        self, event: bytes | Mapping[str, Any]
    ) -> tuple[StreamEvent, ...]:
        if event == NO_STREAM_OUTPUT:
            return (StreamEvent(type="done"),)
        _, raw_payload = decode_sse(event)
        payload = require_object(raw_payload, "stream_event.data")
        if "error" in payload:
            return (StreamEvent(type="error", metadata=require_object(payload["error"], "error")),)
        candidates = payload.get("candidates", [])
        usage = _decode_usage(payload.get("usageMetadata"))
        model = (
            payload.get("modelVersion") if isinstance(payload.get("modelVersion"), str) else None
        )
        if not isinstance(candidates, list) or len(candidates) > 1:
            raise UnsupportedFeatureError(
                "stream_event.candidates", "must contain at most one candidate"
            )
        events: list[StreamEvent] = []
        if not candidates:
            if usage is not None:
                return (StreamEvent(type="usage", usage=usage, model=model),)
            raise UnsupportedFeatureError(
                "stream_event.candidates", "must contain a candidate or usage"
            )
        candidate = require_object(candidates[0], "stream_event.candidates[0]")
        candidate_index = nonnegative_int(
            candidate.get("index", 0), "stream_event.candidates[0].index"
        )
        content = require_object(candidate.get("content", {}), "stream_event.candidate.content")
        base_metadata = vendor_metadata(
            self.protocol,
            payload,
            {"modelVersion", "responseId", "candidates", "usageMetadata"},
        )
        add_vendor_scope(
            base_metadata,
            self.protocol,
            "__candidate__",
            {
                key: item
                for key, item in candidate.items()
                if key not in {"index", "content", "finishReason"}
            },
        )
        add_vendor_scope(
            base_metadata,
            self.protocol,
            "__content__",
            {key: item for key, item in content.items() if key not in {"role", "parts"}},
        )
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            raise UnsupportedFeatureError("stream_event.candidate.content.parts", "must be a list")
        saw_tool_call = False
        for part_index, raw_part in enumerate(parts):
            part = require_object(raw_part, f"stream_event.candidate.content.parts[{part_index}]")
            part_metadata = thaw(base_metadata)
            add_vendor_scope(
                part_metadata,
                self.protocol,
                "__part__",
                {key: item for key, item in part.items() if key not in {"text", "functionCall"}},
            )
            if isinstance(part.get("text"), str):
                events.append(
                    StreamEvent(
                        type="content_delta",
                        index=part_index,
                        text=part["text"],
                        model=model,
                        content_type="text",
                        metadata=part_metadata,
                    )
                )
            elif "functionCall" in part:
                saw_tool_call = True
                call = require_object(part["functionCall"], "stream_event.functionCall")
                add_vendor_scope(
                    part_metadata,
                    self.protocol,
                    "__function_call__",
                    {key: item for key, item in call.items() if key not in {"id", "name", "args"}},
                )
                args = require_object(call.get("args", {}), "stream_event.functionCall.args")
                events.append(
                    StreamEvent(
                        type="tool_call_delta",
                        index=part_index,
                        tool_index=part_index,
                        tool_call_id=(call.get("id") if isinstance(call.get("id"), str) else None),
                        tool_name=(call.get("name") if isinstance(call.get("name"), str) else None),
                        arguments_delta=orjson.dumps(args).decode(),
                        model=model,
                        content_type="tool_call",
                        metadata=part_metadata,
                    )
                )
            else:
                raise UnsupportedFeatureError(
                    f"stream_event.candidate.content.parts[{part_index}]",
                    "unsupported Gemini stream part",
                )
        if candidate.get("finishReason") is not None:
            finish_reason = _decode_finish_reason(candidate.get("finishReason"))
            if candidate.get("finishReason") == "STOP" and saw_tool_call:
                finish_reason = "tool_call"
            events.append(
                StreamEvent(
                    type="message_end",
                    index=candidate_index,
                    finish_reason=finish_reason,
                    model=model,
                    metadata=base_metadata,
                )
            )
        if usage is not None:
            events.append(
                StreamEvent(type="usage", usage=usage, model=model, metadata=base_metadata)
            )
        if not events:
            raise UnsupportedFeatureError("stream_event", "contains no supported delta")
        return tuple(events)

    def encode_stream_event(self, event: StreamEvent) -> bytes:
        if event.type in {"done", "message_start", "content_start", "content_end", "heartbeat"}:
            return NO_STREAM_OUTPUT
        if event.type == "error":
            return encode_sse(
                {
                    "error": {
                        key: thaw(item)
                        for key, item in event.metadata.items()
                        if key != "vendor_extensions"
                    }
                }
            )
        payload = native_extensions(self.protocol, event.metadata)
        _set_optional(payload, "modelVersion", event.model)
        if event.type == "usage":
            if event.usage is None:
                raise UnsupportedFeatureError("stream_event.usage", "is required")
            validate_usage(event.usage, "stream_event.usage")
            payload["candidates"] = []
        else:
            candidate = vendor_scope(self.protocol, event.metadata, "__candidate__")
            candidate["index"] = 0
            if event.type == "content_delta":
                content = vendor_scope(self.protocol, event.metadata, "__content__")
                part = vendor_scope(self.protocol, event.metadata, "__part__")
                part["text"] = event.text or ""
                content.update({"role": "model", "parts": [part]})
                candidate["content"] = content
            elif event.type == "tool_call_delta":
                try:
                    arguments = orjson.loads(event.arguments_delta or "{}")
                except orjson.JSONDecodeError as exc:
                    raise UnsupportedFeatureError(
                        "stream_event.arguments_delta", "Gemini requires complete JSON arguments"
                    ) from exc
                arguments = require_object(arguments, "stream_event.arguments_delta")
                call = vendor_scope(self.protocol, event.metadata, "__function_call__")
                call.update({"name": event.tool_name or "", "args": arguments})
                _set_optional(call, "id", event.tool_call_id)
                content = vendor_scope(self.protocol, event.metadata, "__content__")
                part = vendor_scope(self.protocol, event.metadata, "__part__")
                part["functionCall"] = call
                content.update({"role": "model", "parts": [part]})
                candidate["content"] = content
            elif event.type == "message_end":
                if event.finish_reason is None:
                    raise UnsupportedFeatureError("stream_event.finish_reason", "is required")
                candidate["finishReason"] = _encode_finish_reason(event.finish_reason)
            else:
                raise UnsupportedFeatureError("stream_event.type", f"cannot encode {event.type!r}")
            payload["candidates"] = [candidate]
        if event.usage is not None:
            payload["usageMetadata"] = _encode_usage(event.usage)
        return encode_sse(payload)


class _GeminiStreamDecoder(StreamDecoder):
    def __init__(self) -> None:
        self._adapter = GeminiAdapter()
        self._message_started = False
        self._text_index: int | None = None
        self._open_tools: dict[int, int] = {}
        self._next_part_index = 0
        self._next_tool_index = 0
        self._saw_tool_call = False

    def _ensure_message_start(self, model: str | None) -> list[StreamEvent]:
        if self._message_started:
            return []
        self._message_started = True
        return [StreamEvent(type="message_start", role="assistant", model=model)]

    def _close_text(self, model: str | None = None) -> list[StreamEvent]:
        if self._text_index is None:
            return []
        index = self._text_index
        self._text_index = None
        return [
            StreamEvent(
                type="content_end",
                index=index,
                content_type="text",
                model=model,
            )
        ]

    def _close_tools(self, model: str | None = None) -> list[StreamEvent]:
        events = [
            StreamEvent(
                type="content_end",
                index=block_index,
                tool_index=tool_index,
                content_type="tool_call",
                model=model,
            )
            for tool_index, block_index in sorted(self._open_tools.items())
        ]
        self._open_tools.clear()
        return events

    def decode(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        raw_events = self._adapter._decode_isolated_stream_event(event)
        events: list[StreamEvent] = []
        part_events = [
            raw for raw in raw_events if raw.type in {"content_delta", "tool_call_delta"}
        ]
        multiple_parts = len(part_events) > 1
        seen_part_in_frame = False
        for raw in raw_events:
            if raw.type == "content_delta":
                events.extend(self._ensure_message_start(raw.model))
                if self._text_index is None or (multiple_parts and seen_part_in_frame):
                    events.extend(self._close_text(raw.model))
                    self._text_index = self._next_part_index
                    self._next_part_index += 1
                    events.append(
                        StreamEvent(
                            type="content_start",
                            index=self._text_index,
                            content_type="text",
                            model=raw.model,
                        )
                    )
                events.append(replace(raw, index=self._text_index, content_type="text"))
                seen_part_in_frame = True
            elif raw.type == "tool_call_delta":
                events.extend(self._ensure_message_start(raw.model))
                events.extend(self._close_text(raw.model))
                tool_index = self._next_tool_index
                self._next_tool_index += 1
                block_index = self._next_part_index
                self._next_part_index += 1
                self._open_tools[tool_index] = block_index
                self._saw_tool_call = True
                events.append(
                    replace(
                        raw,
                        index=block_index,
                        tool_index=tool_index,
                        content_type="tool_call",
                    )
                )
                seen_part_in_frame = True
            elif raw.type == "message_end":
                events.extend(self._close_text(raw.model))
                events.extend(self._close_tools(raw.model))
                finish_reason = raw.finish_reason
                if finish_reason == "stop" and self._saw_tool_call:
                    finish_reason = "tool_call"
                events.append(replace(raw, finish_reason=finish_reason))
            elif raw.type == "done":
                events.extend(self._close_text(raw.model))
                events.extend(self._close_tools(raw.model))
                events.append(raw)
            else:
                events.append(raw)
        return tuple(events)


@dataclass(slots=True)
class _GeminiToolBuffer:
    index: int
    tool_index: int | None
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments: list[str] = field(default_factory=list)
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class _GeminiStreamEncoder(StreamEncoder):
    def __init__(self, adapter: GeminiAdapter) -> None:
        self._adapter = adapter
        self._tools: dict[tuple[object, object], _GeminiToolBuffer] = {}

    @staticmethod
    def _key(event: StreamEvent) -> tuple[object, object]:
        if event.tool_index is not None:
            return ("tool_index", event.tool_index)
        if event.tool_call_id is not None:
            return ("tool_call_id", event.tool_call_id)
        return (
            "index",
            event.index,
        )

    def _flush(self, key: tuple[object, object]) -> bytes | None:
        buffer = self._tools.pop(key, None)
        if buffer is None:
            return None
        arguments_text = "".join(buffer.arguments) or "{}"
        try:
            arguments = orjson.loads(arguments_text)
        except orjson.JSONDecodeError as exc:
            raise UnsupportedFeatureError(
                "stream_event.arguments_delta",
                "Gemini requires complete JSON arguments at tool content end",
            ) from exc
        require_object(arguments, "stream_event.arguments_delta")
        return self._adapter.encode_stream_event(
            StreamEvent(
                type="tool_call_delta",
                index=buffer.index,
                tool_index=buffer.tool_index,
                tool_call_id=buffer.tool_call_id,
                tool_name=buffer.tool_name,
                arguments_delta=orjson.dumps(arguments).decode(),
                model=buffer.model,
                content_type="tool_call",
                metadata=buffer.metadata,
            )
        )

    def _flush_all(self) -> list[bytes]:
        frames = []
        for key in list(self._tools):
            frame = self._flush(key)
            if frame:
                frames.append(frame)
        return frames

    def encode(self, event: StreamEvent) -> tuple[bytes, ...]:
        if event.type in {"message_start", "content_start", "heartbeat", "done"}:
            return ()
        if event.type == "tool_call_delta":
            key = self._key(event)
            buffer = self._tools.get(key)
            if buffer is None:
                buffer = _GeminiToolBuffer(index=event.index, tool_index=event.tool_index)
                self._tools[key] = buffer
            if event.tool_call_id is not None:
                buffer.tool_call_id = event.tool_call_id
            if event.tool_name is not None:
                buffer.tool_name = event.tool_name
            if event.arguments_delta is not None:
                buffer.arguments.append(event.arguments_delta)
            if event.model is not None:
                buffer.model = event.model
            if event.metadata:
                buffer.metadata = event.metadata
            return ()
        if event.type == "content_end":
            if event.content_type != "tool_call":
                return ()
            frame = self._flush(self._key(event))
            return (frame,) if frame else ()
        frames: list[bytes] = []
        if event.type == "message_end":
            frames.extend(self._flush_all())
        frame = self._adapter.encode_stream_event(event)
        if frame:
            frames.append(frame)
        return tuple(frames)


def _decode_parts(
    value: Any,
    field: str,
    *,
    role: str | None = None,
) -> tuple[ContentPart, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UnsupportedFeatureError(field, "must be a list")
    result: list[ContentPart] = []
    for index, raw_part in enumerate(value):
        part = require_object(raw_part, f"{field}[{index}]")
        if isinstance(part.get("text"), str):
            result.append(
                TextPart(
                    part["text"],
                    metadata=vendor_metadata(
                        Protocol.GEMINI,
                        part,
                        {"text"},
                    ),
                )
            )
        elif "inlineData" in part or "inline_data" in part:
            if role == "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Gemini image inputs are only valid on user content",
                )
            data = require_object(
                part.get("inlineData", part.get("inline_data")), f"{field}[{index}].inlineData"
            )
            media_type = image_media_type(
                data.get("mimeType", data.get("mime_type")),
                f"{field}[{index}].inlineData.mimeType",
            )
            encoded = data.get("data")
            if not isinstance(encoded, str):
                raise UnsupportedFeatureError(f"{field}[{index}].inlineData", "invalid image")
            metadata = vendor_metadata(
                Protocol.GEMINI,
                part,
                {"inlineData", "inline_data"},
            )
            add_vendor_scope(
                metadata,
                Protocol.GEMINI,
                "__image_data__",
                {
                    key: item
                    for key, item in data.items()
                    if key not in {"mimeType", "mime_type", "data"}
                },
            )
            result.append(
                ImagePart(
                    media_type=media_type,
                    data=encoded,
                    metadata=metadata,
                )
            )
        elif "fileData" in part or "file_data" in part:
            if role == "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Gemini image inputs are only valid on user content",
                )
            data = require_object(
                part.get("fileData", part.get("file_data")), f"{field}[{index}].fileData"
            )
            url = data.get("fileUri", data.get("file_uri"))
            if not isinstance(url, str):
                raise UnsupportedFeatureError(
                    f"{field}[{index}].fileData.fileUri", "must be a string"
                )
            media_type = image_media_type(
                data.get("mimeType", data.get("mime_type")),
                f"{field}[{index}].fileData.mimeType",
            )
            metadata = vendor_metadata(
                Protocol.GEMINI,
                part,
                {"fileData", "file_data"},
            )
            add_vendor_scope(
                metadata,
                Protocol.GEMINI,
                "__image_data__",
                {
                    key: item
                    for key, item in data.items()
                    if key not in {"mimeType", "mime_type", "fileUri", "file_uri"}
                },
            )
            result.append(
                ImagePart(
                    media_type=media_type,
                    url=url,
                    metadata=metadata,
                )
            )
        elif "functionCall" in part or "function_call" in part:
            if role != "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Gemini functionCall parts are only valid on model content",
                )
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
            metadata = vendor_metadata(
                Protocol.GEMINI,
                part,
                {"functionCall", "function_call"},
            )
            add_vendor_scope(
                metadata,
                Protocol.GEMINI,
                "__function_call__",
                {key: item for key, item in call.items() if key not in {"id", "name", "args"}},
            )
            result.append(
                ToolCallPart(
                    id=call_id if isinstance(call_id, str) else None,
                    name=name,
                    arguments=require_object(
                        call.get("args", {}), f"{field}[{index}].functionCall.args"
                    ),
                    metadata=metadata,
                )
            )
        elif "functionResponse" in part or "function_response" in part:
            if role != "user":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Gemini functionResponse parts are only valid on user content",
                )
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
            is_error = False
            if set(response_object) == {"output"} and isinstance(response_object["output"], str):
                text = response_object["output"]
            elif set(response_object) == {"error"} and isinstance(
                response_object["error"], Mapping
            ):
                error = response_object["error"]
                message = error.get("message")
                if not isinstance(message, str):
                    raise UnsupportedFeatureError(
                        f"{field}[{index}].functionResponse.response.error.message",
                        "must be a string",
                    )
                text = message
                is_error = True
            else:
                text = orjson.dumps(response_object, option=orjson.OPT_SORT_KEYS).decode()
            response_id = response.get("id")
            metadata = vendor_metadata(
                Protocol.GEMINI,
                part,
                {"functionResponse", "function_response"},
            )
            add_vendor_scope(
                metadata,
                Protocol.GEMINI,
                "__function_response__",
                {
                    key: item
                    for key, item in response.items()
                    if key not in {"id", "name", "response"}
                },
            )
            result.append(
                ToolResultPart(
                    tool_call_id=response_id if isinstance(response_id, str) else None,
                    name=name,
                    content=(TextPart(text),),
                    is_error=is_error,
                    metadata=metadata,
                )
            )
        else:
            raise UnsupportedFeatureError(f"{field}[{index}]", "unsupported Gemini part")
    return tuple(result)


def _encode_parts(
    parts: Sequence[ContentPart],
    field: str,
    *,
    role: str | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        if isinstance(part, TextPart):
            block = native_extensions(Protocol.GEMINI, part.metadata)
            block["text"] = part.text
            result.append(block)
        elif isinstance(part, ImagePart):
            if role == "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Gemini image inputs are only valid on user content",
                )
            if part.detail is not None:
                raise UnsupportedFeatureError(
                    f"{field}[{index}].detail",
                    "is not supported by Gemini image parts",
                )
            if part.url is not None:
                media_type = part.media_type or image_media_type_from_url(part.url)
                media_type = image_media_type(
                    media_type,
                    f"{field}[{index}].media_type",
                )
                data = vendor_scope(Protocol.GEMINI, part.metadata, "__image_data__")
                data.update(
                    {
                        "mimeType": media_type,
                        "fileUri": part.url,
                    }
                )
                block = {
                    **native_extensions(Protocol.GEMINI, part.metadata),
                    "fileData": data,
                }
            else:
                media_type = image_media_type(
                    part.media_type,
                    f"{field}[{index}].media_type",
                )
                data = vendor_scope(Protocol.GEMINI, part.metadata, "__image_data__")
                data.update({"mimeType": media_type, "data": part.data})
                block = {
                    **native_extensions(Protocol.GEMINI, part.metadata),
                    "inlineData": data,
                }
            result.append(block)
        elif isinstance(part, ToolCallPart):
            if role != "assistant":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Gemini function calls are only valid on assistant messages",
                )
            call = vendor_scope(Protocol.GEMINI, part.metadata, "__function_call__")
            call.update({"name": part.name, "args": thaw(part.arguments)})
            _set_optional(call, "id", part.id)
            block = native_extensions(Protocol.GEMINI, part.metadata)
            block["functionCall"] = call
            result.append(block)
        elif isinstance(part, ToolResultPart):
            if role != "user":
                raise UnsupportedFeatureError(
                    f"{field}[{index}].role",
                    "Gemini function results are only valid on user messages",
                )
            if part.name is None:
                raise UnsupportedFeatureError(f"{field}[{index}].name", "is required by Gemini")
            if len(part.content) != 1 or not isinstance(part.content[0], TextPart):
                raise UnsupportedFeatureError(
                    f"{field}[{index}].content", "Gemini function responses require one text value"
                )
            if not isinstance(part.is_error, bool):
                raise UnsupportedFeatureError(f"{field}[{index}].is_error", "must be a boolean")
            text = part.content[0].text
            response_value = {"error": {"message": text}} if part.is_error else {"output": text}
            response = vendor_scope(Protocol.GEMINI, part.metadata, "__function_response__")
            response.update({"name": part.name, "response": response_value})
            _set_optional(response, "id", part.tool_call_id)
            block = native_extensions(Protocol.GEMINI, part.metadata)
            block["functionResponse"] = response
            result.append(block)
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
            metadata = vendor_metadata(
                Protocol.GEMINI,
                declaration,
                {"name", "description", "parameters"},
            )
            add_vendor_scope(
                metadata,
                Protocol.GEMINI,
                "__group__",
                {
                    key: item
                    for key, item in group.items()
                    if key not in {"functionDeclarations", "function_declarations"}
                },
            )
            result.append(
                CanonicalTool(
                    name=name,
                    description=description if isinstance(description, str) else None,
                    input_schema=require_object(
                        declaration.get("parameters", {}), "tools.functionDeclarations.parameters"
                    ),
                    metadata=metadata,
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
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise UnsupportedFeatureError(
            "toolConfig.functionCallingConfig.allowedFunctionNames",
            "must be a list of strings",
        )
    if len(names) == 1:
        if mode != "ANY":
            raise UnsupportedFeatureError(
                "toolConfig.functionCallingConfig.allowedFunctionNames",
                "requires mode ANY",
            )
        return {"name": names[0]}
    if len(names) > 1:
        if mode != "ANY":
            raise UnsupportedFeatureError(
                "toolConfig.functionCallingConfig.allowedFunctionNames",
                "requires mode ANY",
            )
        return {"names": names}
    choices = {"AUTO": "auto", "NONE": "none", "ANY": "required"}
    if mode not in choices:
        raise UnsupportedFeatureError(
            "toolConfig.functionCallingConfig.mode", f"unsupported {mode!r}"
        )
    return choices[mode]


def _encode_tool_choice(
    value: str | Mapping[str, Any], metadata: Mapping[str, Any]
) -> dict[str, Any]:
    tool_config = vendor_scope(Protocol.GEMINI, metadata, "__tool_config__")
    config = vendor_scope(Protocol.GEMINI, metadata, "__function_calling_config__")
    if isinstance(value, str):
        modes = {"auto": "AUTO", "none": "NONE", "required": "ANY"}
        if value not in modes:
            raise UnsupportedFeatureError("tool_choice", f"unsupported choice {value!r}")
        config["mode"] = modes[value]
    else:
        if "names" in value:
            names = value["names"]
            if (
                not isinstance(names, (list, tuple))
                or not names
                or not all(isinstance(name, str) for name in names)
            ):
                raise UnsupportedFeatureError(
                    "tool_choice.names", "must be a non-empty sequence of strings"
                )
            config.update({"mode": "ANY", "allowedFunctionNames": list(names)})
        else:
            name = value.get("name")
            if not isinstance(name, str):
                raise UnsupportedFeatureError("tool_choice.name", "must be a string")
            config.update({"mode": "ANY", "allowedFunctionNames": [name]})
    tool_config["functionCallingConfig"] = config
    return tool_config


def _decode_usage(value: Any) -> CanonicalUsage | None:
    if value is None:
        return None
    usage = require_object(value, "usageMetadata")
    total_input = nonnegative_int(
        usage.get("promptTokenCount", usage.get("prompt_token_count", 0)),
        "usageMetadata.promptTokenCount",
    )
    cache_read_tokens = nonnegative_int(
        usage.get(
            "cachedContentTokenCount",
            usage.get("cached_content_token_count", 0),
        ),
        "usageMetadata.cachedContentTokenCount",
    )
    input_tokens = total_input - cache_read_tokens
    if input_tokens < 0:
        raise UnsupportedFeatureError(
            "usageMetadata.promptTokenCount",
            "cache token details exceed total input tokens",
        )
    output_tokens = nonnegative_int(
        usage.get("candidatesTokenCount", usage.get("candidates_token_count", 0)),
        "usageMetadata.candidatesTokenCount",
    )
    return CanonicalUsage(input_tokens, output_tokens, cache_read_tokens)


def _encode_usage(usage: CanonicalUsage) -> dict[str, int]:
    validate_usage(usage)
    total_input = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    encoded = {
        "promptTokenCount": total_input,
        "candidatesTokenCount": usage.output_tokens,
        "totalTokenCount": total_input + usage.output_tokens,
    }
    if usage.cache_read_tokens:
        encoded["cachedContentTokenCount"] = usage.cache_read_tokens
    return encoded


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
    if value == "error":
        raise UnsupportedFeatureError(
            "finish_reason", "Gemini errors must be encoded as an error object"
        )
    return {
        "stop": "STOP",
        "length": "MAX_TOKENS",
        "tool_call": "STOP",
        "content_filter": "SAFETY",
    }[value]


def _encode_message(message: CanonicalMessage, index: int) -> dict[str, Any]:
    payload = native_extensions(Protocol.GEMINI, message.metadata)
    payload.update(
        {
            "role": "model" if message.role == "assistant" else "user",
            "parts": _encode_parts(
                message.content,
                f"messages[{index}].content",
                role=message.role,
            ),
        }
    )
    return payload


def _encode_tool_group(tools: Sequence[CanonicalTool]) -> dict[str, Any]:
    group = vendor_scope(Protocol.GEMINI, tools[0].metadata, "__group__")
    declarations = []
    for tool in tools:
        declaration = native_extensions(Protocol.GEMINI, tool.metadata)
        declaration.update(
            {
                "name": tool.name,
                **({"description": tool.description} if tool.description is not None else {}),
                "parameters": thaw(tool.input_schema),
            }
        )
        declarations.append(declaration)
    group["functionDeclarations"] = declarations
    return group


def _capture_config_extensions(
    metadata: dict[str, Any],
    tool_config_value: Any,
    generation: Mapping[str, Any],
) -> None:
    if isinstance(tool_config_value, Mapping):
        add_vendor_scope(
            metadata,
            Protocol.GEMINI,
            "__tool_config__",
            {
                key: item
                for key, item in tool_config_value.items()
                if key not in {"functionCallingConfig", "function_calling_config"}
            },
        )
        calling = tool_config_value.get(
            "functionCallingConfig",
            tool_config_value.get("function_calling_config"),
        )
        if isinstance(calling, Mapping):
            add_vendor_scope(
                metadata,
                Protocol.GEMINI,
                "__function_calling_config__",
                {
                    key: item
                    for key, item in calling.items()
                    if key not in {"mode", "allowedFunctionNames", "allowed_function_names"}
                },
            )
    add_vendor_scope(
        metadata,
        Protocol.GEMINI,
        "__generation_config__",
        {
            key: item
            for key, item in generation.items()
            if key not in {"temperature", "topP", "maxOutputTokens", "stopSequences"}
        },
    )


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        payload[key] = value
