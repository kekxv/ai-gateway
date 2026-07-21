"""Protocol-neutral chat contracts and native protocol adapters."""

from ai_gateway.protocols.base import (
    CROSS_PROTOCOL_LOSSES,
    NO_STREAM_OUTPUT,
    ProtocolAdapter,
    UnsupportedFeatureError,
    rewrite_passthrough_request,
    rewrite_passthrough_sse,
)
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import (
    CanonicalMessage,
    CanonicalRequest,
    CanonicalResponse,
    CanonicalTool,
    CanonicalUsage,
    ImagePart,
    StreamEvent,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)

__all__ = [
    "CROSS_PROTOCOL_LOSSES",
    "CanonicalMessage",
    "CanonicalRequest",
    "CanonicalResponse",
    "CanonicalTool",
    "CanonicalUsage",
    "ImagePart",
    "NO_STREAM_OUTPUT",
    "ProtocolAdapter",
    "StreamEvent",
    "TextPart",
    "ToolCallPart",
    "ToolResultPart",
    "UnsupportedFeatureError",
    "get_adapter",
    "rewrite_passthrough_request",
    "rewrite_passthrough_sse",
]
