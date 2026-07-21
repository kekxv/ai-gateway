from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import orjson
import tiktoken
from tiktoken import Encoding

from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.protocols.base import nonnegative_int, thaw
from ai_gateway.protocols.types import (
    CanonicalRequest,
    CanonicalUsage,
    ContentPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)


@dataclass(frozen=True, slots=True)
class UsageResult:
    usage: CanonicalUsage
    usage_source: UsageSource


def extract_provider_usage(
    protocol: Protocol | str,
    payload: Mapping[str, Any],
) -> CanonicalUsage | None:
    selected_protocol = Protocol(protocol)
    if selected_protocol is Protocol.OPENAI:
        usage = _mapping(payload.get("usage"))
        if usage is None:
            return None
        return CanonicalUsage(
            input_tokens=nonnegative_int(usage.get("prompt_tokens", 0), "usage.prompt_tokens"),
            output_tokens=nonnegative_int(
                usage.get("completion_tokens", 0), "usage.completion_tokens"
            ),
        )
    if selected_protocol is Protocol.CLAUDE:
        usage = _mapping(payload.get("usage"))
        if usage is None:
            return None
        return CanonicalUsage(
            input_tokens=nonnegative_int(usage.get("input_tokens", 0), "usage.input_tokens"),
            output_tokens=nonnegative_int(usage.get("output_tokens", 0), "usage.output_tokens"),
        )

    usage = _mapping(payload.get("usageMetadata"))
    if usage is None:
        return None
    return CanonicalUsage(
        input_tokens=nonnegative_int(
            usage.get("promptTokenCount", usage.get("prompt_token_count", 0)),
            "usageMetadata.promptTokenCount",
        ),
        output_tokens=nonnegative_int(
            usage.get("candidatesTokenCount", usage.get("candidates_token_count", 0)),
            "usageMetadata.candidatesTokenCount",
        ),
    )


def estimate_request_tokens(request: CanonicalRequest) -> int:
    values: list[str] = []
    values.extend(_content_strings(request.system))
    for message in request.messages:
        values.extend(_content_strings(message.content))
    for tool in request.tools:
        values.append(tool.name)
        if tool.description is not None:
            values.append(tool.description)
        values.append(orjson.dumps(thaw(tool.input_schema), option=orjson.OPT_SORT_KEYS).decode())
    return sum(estimate_text_tokens(value) for value in values)


def estimate_text_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def resolve_usage(
    *,
    protocol: Protocol | str,
    payload: Mapping[str, Any],
    request: CanonicalRequest,
    response_text: str,
) -> UsageResult:
    provider_usage = extract_provider_usage(protocol, payload)
    if provider_usage is not None:
        return UsageResult(provider_usage, UsageSource.PROVIDER)
    return UsageResult(
        usage=CanonicalUsage(
            input_tokens=estimate_request_tokens(request),
            output_tokens=estimate_text_tokens(response_text),
        ),
        usage_source=UsageSource.ESTIMATED,
    )


def _content_strings(parts: Sequence[ContentPart]) -> list[str]:
    values: list[str] = []
    for part in parts:
        if isinstance(part, TextPart):
            values.append(part.text)
        elif isinstance(part, ToolCallPart):
            values.extend(
                (
                    part.name,
                    orjson.dumps(thaw(part.arguments), option=orjson.OPT_SORT_KEYS).decode(),
                )
            )
        elif isinstance(part, ToolResultPart):
            if part.name is not None:
                values.append(part.name)
            values.extend(_content_strings(part.content))
    return values


def _mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError("provider usage must be an object")
    return value


@lru_cache
def _encoding() -> Encoding:
    return tiktoken.get_encoding("cl100k_base")
