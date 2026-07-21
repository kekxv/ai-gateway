from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, cast

type JsonMapping = Mapping[str, Any]
type MessageRole = Literal["user", "assistant"]
type FinishReason = Literal["stop", "length", "tool_call", "content_filter", "error"]
type StreamEventType = Literal[
    "message_start",
    "content_delta",
    "content_end",
    "tool_call_delta",
    "message_end",
    "usage",
    "heartbeat",
    "error",
    "done",
]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class ImagePart:
    media_type: str | None = None
    data: str | None = None
    url: str | None = None
    detail: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.data is None) == (self.url is None):
            raise ValueError("exactly one of ImagePart.data or ImagePart.url is required")
        if self.data is not None and self.media_type is None:
            raise ValueError("ImagePart.media_type is required for base64 data")
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class ToolCallPart:
    id: str | None
    name: str
    arguments: JsonMapping
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze(self.arguments))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class ToolResultPart:
    tool_call_id: str | None
    name: str | None
    content: Sequence[TextPart | ImagePart]
    is_error: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", tuple(self.content))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


type ContentPart = TextPart | ImagePart | ToolCallPart | ToolResultPart


@dataclass(frozen=True, slots=True)
class CanonicalMessage:
    role: MessageRole
    content: Sequence[ContentPart]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", tuple(self.content))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class CanonicalTool:
    name: str
    description: str | None
    input_schema: JsonMapping
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_schema", _freeze(self.input_schema))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class CanonicalUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class CanonicalRequest:
    model: str
    messages: Sequence[CanonicalMessage]
    system: Sequence[ContentPart]
    tools: Sequence[CanonicalTool]
    tool_choice: str | dict[str, Any] | None
    temperature: float | None
    top_p: float | None
    max_output_tokens: int | None
    stop_sequences: Sequence[str]
    stream: bool
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "system", tuple(self.system))
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "stop_sequences", tuple(self.stop_sequences))
        if isinstance(self.tool_choice, dict):
            object.__setattr__(self, "tool_choice", cast(dict[str, Any], _freeze(self.tool_choice)))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class CanonicalResponse:
    model: str
    message: CanonicalMessage
    finish_reason: FinishReason
    usage: CanonicalUsage | None
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class StreamEvent:
    type: StreamEventType
    index: int = 0
    text: str | None = None
    role: MessageRole | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_delta: str | None = None
    finish_reason: FinishReason | None = None
    usage: CanonicalUsage | None = None
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))
