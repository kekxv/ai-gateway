import orjson
import pytest
import tiktoken

from ai_gateway.billing.usage import (
    estimate_request_tokens,
    extract_native_openai_usage,
    extract_provider_usage,
    resolve_usage,
)
from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.protocols.base import UnsupportedFeatureError
from ai_gateway.protocols.types import (
    CanonicalMessage,
    CanonicalRequest,
    CanonicalTool,
    CanonicalUsage,
    TextPart,
)


@pytest.mark.parametrize(
    ("protocol", "payload"),
    [
        (
            Protocol.OPENAI,
            {"usage": {"prompt_tokens": 17, "completion_tokens": 5}},
        ),
        (
            Protocol.CLAUDE,
            {"usage": {"input_tokens": 17, "output_tokens": 5}},
        ),
        (
            Protocol.GEMINI,
            {"usageMetadata": {"promptTokenCount": 17, "candidatesTokenCount": 5}},
        ),
    ],
)
def test_extracts_provider_usage(protocol: Protocol, payload: dict[str, object]) -> None:
    assert extract_provider_usage(protocol, payload) == CanonicalUsage(17, 5)


@pytest.mark.parametrize(
    ("protocol", "payload", "expected"),
    [
        (
            Protocol.OPENAI,
            {
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 7,
                    "prompt_tokens_details": {
                        "cached_tokens": 10,
                        "cache_write_tokens": 4,
                    },
                }
            },
            (86, 7, 10, 4),
        ),
        (
            Protocol.CLAUDE,
            {
                "usage": {
                    "input_tokens": 6,
                    "output_tokens": 7,
                    "cache_read_input_tokens": 10,
                    "cache_creation_input_tokens": 4,
                }
            },
            (6, 7, 10, 4),
        ),
        (
            Protocol.GEMINI,
            {
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 7,
                    "cachedContentTokenCount": 10,
                }
            },
            (90, 7, 10, 0),
        ),
    ],
)
def test_extracts_mutually_exclusive_cache_usage(
    protocol: Protocol,
    payload: dict[str, object],
    expected: tuple[int, int, int, int],
) -> None:
    usage = extract_provider_usage(protocol, payload)

    assert usage is not None
    assert (
        usage.input_tokens,
        usage.output_tokens,
        getattr(usage, "cache_read_tokens", None),
        getattr(usage, "cache_write_tokens", None),
    ) == expected


def test_estimate_request_tokens_counts_text_and_tool_schema_json() -> None:
    request = _request()
    encoding = tiktoken.get_encoding("cl100k_base")
    expected = sum(
        len(encoding.encode(value))
        for value in (
            "Follow the policy.",
            "hello from the user",
            "lookup",
            "Look up a record",
            orjson.dumps(
                {"type": "object", "properties": {"id": {"type": "integer"}}},
                option=orjson.OPT_SORT_KEYS,
            ).decode(),
        )
    )

    assert estimate_request_tokens(request) == expected


def test_missing_usage_estimates_request_and_response_and_marks_source() -> None:
    request = _request()
    response_text = "estimated response text"
    encoding = tiktoken.get_encoding("cl100k_base")

    result = resolve_usage(
        protocol=Protocol.OPENAI,
        payload={"id": "response-without-usage"},
        request=request,
        response_text=response_text,
    )

    assert result.usage == CanonicalUsage(
        input_tokens=estimate_request_tokens(request),
        output_tokens=len(encoding.encode(response_text)),
    )
    assert result.usage_source is UsageSource.ESTIMATED


def test_provider_usage_wins_over_estimation() -> None:
    result = resolve_usage(
        protocol=Protocol.CLAUDE,
        payload={"usage": {"input_tokens": 31, "output_tokens": 9}},
        request=_request(),
        response_text="this must not be estimated",
    )

    assert result.usage == CanonicalUsage(31, 9)
    assert result.usage_source is UsageSource.PROVIDER


@pytest.mark.parametrize(
    ("operation", "payload", "expected"),
    [
        (
            "responses",
            {"usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}},
            CanonicalUsage(11, 7),
        ),
        (
            "embeddings",
            {"usage": {"prompt_tokens": 9, "total_tokens": 9}},
            CanonicalUsage(9, 0),
        ),
        (
            "completions",
            {"usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}},
            CanonicalUsage(4, 2),
        ),
    ],
)
def test_extracts_usage_for_each_native_openai_operation(
    operation: str,
    payload: dict[str, object],
    expected: CanonicalUsage,
) -> None:
    assert extract_native_openai_usage(operation, payload) == expected


def test_extracts_native_openai_responses_cache_usage() -> None:
    payload = {
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {
                "cached_tokens": 10,
                "cache_write_tokens": 4,
            },
        }
    }

    usage = extract_native_openai_usage("responses", payload)

    assert usage is not None
    assert (
        usage.input_tokens,
        usage.output_tokens,
        getattr(usage, "cache_read_tokens", None),
        getattr(usage, "cache_write_tokens", None),
    ) == (86, 20, 10, 4)


@pytest.mark.parametrize(
    ("protocol", "payload"),
    [
        (
            Protocol.OPENAI,
            {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 1,
                    "prompt_tokens_details": {
                        "cached_tokens": 8,
                        "cache_write_tokens": 4,
                    },
                }
            },
        ),
        (
            Protocol.GEMINI,
            {
                "usageMetadata": {
                    "promptTokenCount": 5,
                    "candidatesTokenCount": 1,
                    "cachedContentTokenCount": 6,
                }
            },
        ),
    ],
)
def test_rejects_cache_details_larger_than_total_input(
    protocol: Protocol,
    payload: dict[str, object],
) -> None:
    with pytest.raises(UnsupportedFeatureError, match="cache token details exceed"):
        extract_provider_usage(protocol, payload)


@pytest.mark.parametrize(
    ("protocol", "payload"),
    [
        (Protocol.OPENAI, {"usage": {"prompt_tokens": 31}}),
        (Protocol.CLAUDE, {"usage": {"output_tokens": 9}}),
        (Protocol.GEMINI, {"usageMetadata": {"promptTokenCount": 31}}),
    ],
)
def test_partial_provider_usage_falls_back_to_complete_estimate(
    protocol: Protocol,
    payload: dict[str, object],
) -> None:
    request = _request()
    response_text = "complete estimated response"
    encoding = tiktoken.get_encoding("cl100k_base")

    result = resolve_usage(
        protocol=protocol,
        payload=payload,
        request=request,
        response_text=response_text,
    )

    assert result.usage == CanonicalUsage(
        estimate_request_tokens(request),
        len(encoding.encode(response_text)),
    )
    assert result.usage_source is UsageSource.ESTIMATED


def _request() -> CanonicalRequest:
    return CanonicalRequest(
        model="priced-model",
        messages=(CanonicalMessage(role="user", content=(TextPart("hello from the user"),)),),
        system=(TextPart("Follow the policy."),),
        tools=(
            CanonicalTool(
                name="lookup",
                description="Look up a record",
                input_schema={
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                },
            ),
        ),
        tool_choice=None,
        temperature=None,
        top_p=None,
        max_output_tokens=None,
        stop_sequences=(),
        stream=False,
        metadata={},
    )
