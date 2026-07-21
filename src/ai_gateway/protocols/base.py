from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, TypeGuard, cast

import orjson

from ai_gateway.core.enums import Protocol
from ai_gateway.core.errors import GatewayError
from ai_gateway.protocols.types import (
    CanonicalRequest,
    CanonicalResponse,
    CanonicalUsage,
    StreamEvent,
)

# These are the only intentional semantic losses at this conversion layer. Native extensions are
# protocol-scoped so they survive same-protocol canonical round trips without leaking to another
# provider. Claude content-delta frames do not carry a model name, so cross-protocol stream tests
# compare the event payload independently of that optional envelope field.
CROSS_PROTOCOL_LOSSES = (
    "metadata.vendor_extensions are emitted only to the protocol that supplied them",
    "Claude content delta events do not carry the optional stream model envelope",
    "an empty encoded stream frame means the target protocol has no wire event for that "
    "canonical event",
)

# Encoders return this when a canonical event has no native frame. Streaming orchestration must
# skip it. Gemini decoding interprets an empty input only when the HTTP response reaches EOF, where
# it becomes the canonical `done` event; callers must not feed ordinary encoder no-ops back in.
NO_STREAM_OUTPUT = b""


class UnsupportedFeatureError(GatewayError):
    code = "unsupported_feature"
    status_code = 422

    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        super().__init__(f"{field}: {detail}")


class StreamDecoder(ABC):
    """State retained while incrementally decoding one native response stream."""

    @abstractmethod
    def decode(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]: ...


class StreamEncoder(ABC):
    """State retained while incrementally encoding one native response stream."""

    @abstractmethod
    def encode(self, event: StreamEvent) -> tuple[bytes, ...]: ...


class ProtocolAdapter(ABC):
    protocol: Protocol

    @abstractmethod
    def decode_request(self, payload: Mapping[str, Any]) -> CanonicalRequest: ...

    @abstractmethod
    def encode_request(self, request: CanonicalRequest) -> dict[str, Any]: ...

    @abstractmethod
    def decode_response(self, payload: Mapping[str, Any]) -> CanonicalResponse: ...

    @abstractmethod
    def encode_response(self, response: CanonicalResponse) -> dict[str, Any]: ...

    @abstractmethod
    def create_stream_decoder(self) -> StreamDecoder: ...

    @abstractmethod
    def create_stream_encoder(self) -> StreamEncoder: ...

    @abstractmethod
    def decode_stream_event(self, event: bytes | Mapping[str, Any]) -> tuple[StreamEvent, ...]:
        """Decode one isolated frame; use create_stream_decoder for a complete stream."""
        ...

    @abstractmethod
    def encode_stream_event(self, event: StreamEvent) -> bytes:
        """Encode one isolated event; use create_stream_encoder for a complete stream."""
        ...


def rewrite_passthrough_request(
    protocol: Protocol | str,
    raw_body: bytes,
    upstream_model: str,
) -> bytes:
    Protocol(protocol)
    payload = orjson.loads(raw_body)
    if not is_object(payload):
        raise ValueError("request body must be one JSON object")
    payload["model"] = upstream_model
    return orjson.dumps(payload)


def rewrite_passthrough_sse(event: bytes) -> bytes:
    return event


def is_object(value: Any) -> TypeGuard[dict[str, Any]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def require_object(value: Any, field: str) -> dict[str, Any]:
    if not is_object(value):
        raise UnsupportedFeatureError(field, "must be a JSON object")
    return value


def optional_float(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UnsupportedFeatureError(field, "must be a number")
    return float(value)


def optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnsupportedFeatureError(field, "must be an integer")
    return value


def nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnsupportedFeatureError(field, "must be an integer")
    if value < 0:
        raise UnsupportedFeatureError(field, "must be nonnegative")
    return value


def validate_usage(usage: CanonicalUsage, field: str = "usage") -> CanonicalUsage:
    nonnegative_int(usage.input_tokens, f"{field}.input_tokens")
    nonnegative_int(usage.output_tokens, f"{field}.output_tokens")
    return usage


def required_bool(value: Any, field: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise UnsupportedFeatureError(field, "must be a boolean")
    return value


def string_list(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise UnsupportedFeatureError(field, "must be a string or list of strings")
    return tuple(values)


def json_arguments(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = orjson.loads(value)
        except orjson.JSONDecodeError as exc:
            raise UnsupportedFeatureError(field, "must contain a complete JSON object") from exc
    return require_object(value, field)


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


def vendor_metadata(
    protocol: Protocol,
    payload: Mapping[str, Any],
    known_fields: set[str],
    **common: Any,
) -> dict[str, Any]:
    extensions = {key: thaw(value) for key, value in payload.items() if key not in known_fields}
    metadata = {key: value for key, value in common.items() if value is not None}
    if extensions:
        metadata["vendor_extensions"] = {protocol.value: extensions}
    return metadata


def add_vendor_scope(
    metadata: dict[str, Any],
    protocol: Protocol,
    scope: str,
    extensions: Mapping[str, Any],
) -> None:
    if not extensions:
        return
    all_extensions = metadata.setdefault("vendor_extensions", {})
    protocol_extensions = all_extensions.setdefault(protocol.value, {})
    protocol_extensions[scope] = thaw(extensions)


def native_extensions(protocol: Protocol, metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return extensions only for their originating protocol to prevent vendor leakage."""
    all_extensions = metadata.get("vendor_extensions")
    if not isinstance(all_extensions, Mapping):
        return {}
    extensions = all_extensions.get(protocol.value)
    if not isinstance(extensions, Mapping):
        return {}
    return {key: thaw(value) for key, value in extensions.items() if not str(key).startswith("__")}


def vendor_scope(
    protocol: Protocol,
    metadata: Mapping[str, Any],
    scope: str,
) -> dict[str, Any]:
    all_extensions = metadata.get("vendor_extensions")
    if not isinstance(all_extensions, Mapping):
        return {}
    extensions = all_extensions.get(protocol.value)
    if not isinstance(extensions, Mapping):
        return {}
    scoped = extensions.get(scope)
    return cast(dict[str, Any], thaw(scoped)) if isinstance(scoped, Mapping) else {}


def decode_sse(event: bytes | Mapping[str, Any]) -> tuple[str | None, Any]:
    if isinstance(event, Mapping):
        return None, thaw(event)
    event_name: str | None = None
    data_lines: list[bytes] = []
    for line in event.replace(b"\r\n", b"\n").split(b"\n"):
        if line.startswith(b"event:"):
            event_name = line[6:].lstrip().decode("utf-8")
        elif line.startswith(b"data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        raise UnsupportedFeatureError("stream_event", "SSE event has no data field")
    data = b"\n".join(data_lines)
    if data == b"[DONE]":
        return event_name, "[DONE]"
    try:
        return event_name, orjson.loads(data)
    except orjson.JSONDecodeError as exc:
        raise UnsupportedFeatureError("stream_event.data", "must contain JSON") from exc


def encode_sse(payload: Mapping[str, Any] | str, event_name: str | None = None) -> bytes:
    data = payload.encode() if isinstance(payload, str) else orjson.dumps(payload)
    prefix = b"" if event_name is None else b"event: " + event_name.encode() + b"\n"
    return prefix + b"data: " + data + b"\n\n"
