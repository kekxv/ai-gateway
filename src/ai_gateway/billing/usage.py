from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import orjson
import tiktoken
from tiktoken import Encoding

from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.protocols.base import UnsupportedFeatureError, nonnegative_int, thaw
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


def extract_native_openai_usage(
    operation: str,
    payload: Mapping[str, Any],
) -> CanonicalUsage | None:
    usage = _mapping(payload.get("usage"))
    if usage is None:
        return None
    if operation == "responses":
        if not _has_fields(usage, "input_tokens", "output_tokens"):
            return None
        total_input = nonnegative_int(usage["input_tokens"], "usage.input_tokens")
        cache_read, cache_write = _openai_cache_tokens(usage, "input_tokens_details")
        return CanonicalUsage(
            input_tokens=_exclusive_input(
                total_input,
                cache_read,
                cache_write,
                "usage.input_tokens",
            ),
            output_tokens=nonnegative_int(usage["output_tokens"], "usage.output_tokens"),
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
    if operation == "embeddings":
        if "prompt_tokens" not in usage:
            return None
        return CanonicalUsage(
            input_tokens=nonnegative_int(usage["prompt_tokens"], "usage.prompt_tokens"),
            output_tokens=0,
        )
    if not _has_fields(usage, "prompt_tokens", "completion_tokens"):
        return None
    total_input = nonnegative_int(usage["prompt_tokens"], "usage.prompt_tokens")
    cache_read, cache_write = _openai_cache_tokens(usage, "prompt_tokens_details")
    return CanonicalUsage(
        input_tokens=_exclusive_input(total_input, cache_read, cache_write, "usage.prompt_tokens"),
        output_tokens=nonnegative_int(usage["completion_tokens"], "usage.completion_tokens"),
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )


def extract_provider_usage(
    protocol: Protocol | str,
    payload: Mapping[str, Any],
) -> CanonicalUsage | None:
    selected_protocol = Protocol(protocol)
    if selected_protocol is Protocol.OPENAI:
        usage = _mapping(payload.get("usage"))
        if usage is None or not _has_fields(usage, "prompt_tokens", "completion_tokens"):
            return None
        total_input = nonnegative_int(usage["prompt_tokens"], "usage.prompt_tokens")
        cache_read, cache_write = _openai_cache_tokens(usage, "prompt_tokens_details")
        return CanonicalUsage(
            input_tokens=_exclusive_input(
                total_input,
                cache_read,
                cache_write,
                "usage.prompt_tokens",
            ),
            output_tokens=nonnegative_int(usage["completion_tokens"], "usage.completion_tokens"),
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
    if selected_protocol is Protocol.CLAUDE:
        usage = _mapping(payload.get("usage"))
        if usage is None or not _has_fields(usage, "input_tokens", "output_tokens"):
            return None
        return CanonicalUsage(
            input_tokens=nonnegative_int(usage["input_tokens"], "usage.input_tokens"),
            output_tokens=nonnegative_int(usage["output_tokens"], "usage.output_tokens"),
            cache_read_tokens=nonnegative_int(
                usage.get("cache_read_input_tokens", 0),
                "usage.cache_read_input_tokens",
            ),
            cache_write_tokens=nonnegative_int(
                usage.get("cache_creation_input_tokens", 0),
                "usage.cache_creation_input_tokens",
            ),
        )

    usage = _mapping(payload.get("usageMetadata"))
    if usage is None:
        return None
    input_key = _first_present(usage, "promptTokenCount", "prompt_token_count")
    output_key = _first_present(usage, "candidatesTokenCount", "candidates_token_count")
    if input_key is None or output_key is None:
        return None
    total_input = nonnegative_int(usage[input_key], "usageMetadata.promptTokenCount")
    cached_key = _first_present(
        usage,
        "cachedContentTokenCount",
        "cached_content_token_count",
    )
    cache_read = nonnegative_int(
        usage[cached_key] if cached_key is not None else 0,
        "usageMetadata.cachedContentTokenCount",
    )
    return CanonicalUsage(
        input_tokens=_exclusive_input(
            total_input,
            cache_read,
            0,
            "usageMetadata.promptTokenCount",
        ),
        output_tokens=nonnegative_int(
            usage[output_key],
            "usageMetadata.candidatesTokenCount",
        ),
        cache_read_tokens=cache_read,
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


async def estimate_request_tokens_async(request: CanonicalRequest) -> int:
    return await asyncio.to_thread(estimate_request_tokens, request)


async def warm_tokenizer() -> None:
    await asyncio.to_thread(_encoding)


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


async def resolve_usage_async(
    *,
    protocol: Protocol | str,
    payload: Mapping[str, Any],
    request: CanonicalRequest,
    response_text: str,
) -> UsageResult:
    return await asyncio.to_thread(
        resolve_usage,
        protocol=protocol,
        payload=payload,
        request=request,
        response_text=response_text,
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


def _has_fields(value: Mapping[str, Any], *fields: str) -> bool:
    return all(field in value for field in fields)


def _first_present(value: Mapping[str, Any], *fields: str) -> str | None:
    return next((field for field in fields if field in value), None)


def _openai_cache_tokens(
    usage: Mapping[str, Any],
    details_field: str,
) -> tuple[int, int]:
    details = _mapping(usage.get(details_field))
    if details is None:
        return 0, 0
    return (
        nonnegative_int(details.get("cached_tokens", 0), f"usage.{details_field}.cached_tokens"),
        nonnegative_int(
            details.get("cache_write_tokens", 0),
            f"usage.{details_field}.cache_write_tokens",
        ),
    )


def _exclusive_input(total: int, cache_read: int, cache_write: int, field: str) -> int:
    uncached = total - cache_read - cache_write
    if uncached < 0:
        raise UnsupportedFeatureError(field, "cache token details exceed total input tokens")
    return uncached


@lru_cache
def _encoding() -> Encoding:
    return tiktoken.get_encoding("cl100k_base")
