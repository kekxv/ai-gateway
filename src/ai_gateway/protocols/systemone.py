from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import orjson

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import (
    ProtocolAdapter,
    StreamDecoder,
    StreamEncoder,
    UnsupportedFeatureError,
)
from ai_gateway.protocols.types import (
    CanonicalMessage,
    CanonicalRequest,
    CanonicalResponse,
    CanonicalUsage,
    StreamEvent,
    TextPart,
)


class _NoStream(StreamDecoder, StreamEncoder):
    def decode(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        raise UnsupportedFeatureError("stream", "System One does not support streaming")

    def encode(self, event: StreamEvent) -> tuple[bytes, ...]:
        raise UnsupportedFeatureError("stream", "System One does not support streaming")


class SystemOneAdapter(ProtocolAdapter):
    protocol = Protocol.SYSTEMONE

    def decode_request(self, payload: Mapping[str, Any]) -> CanonicalRequest:
        model = payload.get("model")
        if not isinstance(model, str) or not model:
            raise UnsupportedFeatureError("model", "must be a non-empty string")
        state = payload.get("state")
        if not isinstance(state, (str, Mapping, list)):
            raise UnsupportedFeatureError("state", "must be a string, object, or array")
        questions = payload.get("questions")
        if not isinstance(questions, Mapping) or not questions:
            raise UnsupportedFeatureError("questions", "must be a non-empty object")
        for key, question in questions.items():
            if not isinstance(key, str) or not key or not isinstance(question, Mapping):
                raise UnsupportedFeatureError("questions", "question ids and values must be valid")
            kind = question.get("type")
            if kind not in {"choice", "score", "noul"}:
                raise UnsupportedFeatureError(
                    f"questions.{key}.type", "must be choice, score, or noul"
                )
            if "instructions" not in question:
                raise UnsupportedFeatureError(f"questions.{key}.instructions", "is required")
            if kind == "choice" and not isinstance(question.get("criteria"), Mapping):
                raise UnsupportedFeatureError(
                    f"questions.{key}.criteria", "must be an object for choice"
                )
            if kind == "score" and not isinstance(question.get("criteria"), list):
                raise UnsupportedFeatureError(
                    f"questions.{key}.criteria", "must be an array for score"
                )
        if payload.get("stream") is True:
            raise UnsupportedFeatureError("stream", "System One does not support streaming")
        return CanonicalRequest(
            model=model,
            messages=(
                CanonicalMessage(
                    role="user",
                    content=(TextPart(orjson.dumps(payload).decode()),),
                ),
            ),
            system=(),
            tools=(),
            tool_choice=None,
            temperature=None,
            top_p=None,
            max_output_tokens=None,
            stop_sequences=(),
            stream=False,
            metadata={"systemone_payload": dict(payload)},
        )

    def encode_request(self, request: CanonicalRequest) -> dict[str, Any]:
        payload = dict(request.metadata.get("systemone_payload", {}))
        payload["model"] = request.model
        return payload

    def decode_response(self, payload: Mapping[str, Any]) -> CanonicalResponse:
        raw_usage = payload.get("usage")
        usage = None
        if isinstance(raw_usage, Mapping):
            usage = CanonicalUsage(
                int(raw_usage.get("input_tokens", 0)), int(raw_usage.get("output_tokens", 0))
            )
        return CanonicalResponse(
            model=str(payload.get("model", "")),
            message=CanonicalMessage(role="assistant", content=(TextPart(""),)),
            finish_reason="stop",
            usage=usage,
            metadata={"systemone_response": dict(payload)},
        )

    def encode_response(self, response: CanonicalResponse) -> dict[str, Any]:
        return dict(response.metadata.get("systemone_response", {}))

    def create_stream_decoder(self) -> StreamDecoder:
        return _NoStream()

    def create_stream_encoder(self) -> StreamEncoder:
        return _NoStream()

    def decode_stream_event(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        raise UnsupportedFeatureError("stream", "System One does not support streaming")

    def encode_stream_event(self, event: StreamEvent) -> bytes:
        raise UnsupportedFeatureError("stream", "System One does not support streaming")
