from __future__ import annotations

from dataclasses import replace

import pytest

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import UnsupportedFeatureError
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import (
    CanonicalMessage,
    CanonicalRequest,
    CanonicalUsage,
    ImagePart,
    StreamEvent,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)


def _request(message: CanonicalMessage) -> CanonicalRequest:
    return CanonicalRequest(
        model="model",
        messages=(message,),
        system=(),
        tools=(),
        tool_choice=None,
        temperature=None,
        top_p=None,
        max_output_tokens=None,
        stop_sequences=(),
        stream=False,
        metadata={},
    )


@pytest.mark.parametrize("protocol", tuple(Protocol))
@pytest.mark.parametrize("bad_stream", ["false", 0, 1, [], {}])
def test_stream_requires_a_real_boolean(protocol, bad_stream, load_fixture) -> None:
    payload = load_fixture(protocol.value, "request.json")
    payload["stream"] = bad_stream

    with pytest.raises(UnsupportedFeatureError, match="stream"):
        get_adapter(protocol).decode_request(payload)


def test_openai_rejects_tool_parts_on_wrong_roles(load_fixture) -> None:
    adapter = get_adapter("openai")
    payload = load_fixture("openai", "request.json")
    payload["messages"][1]["tool_calls"] = [
        {"id": "x", "type": "function", "function": {"name": "f", "arguments": "{}"}}
    ]
    payload["messages"][1]["role"] = "user"

    with pytest.raises(UnsupportedFeatureError, match=r"messages\[1\]\.tool_calls"):
        adapter.decode_request(payload)
    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\].*role"):
        adapter.encode_request(_request(CanonicalMessage("user", (ToolCallPart("x", "f", {}),))))
    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\].*role"):
        adapter.encode_request(
            _request(CanonicalMessage("assistant", (ToolResultPart("x", "f", (TextPart("ok"),)),)))
        )


@pytest.mark.parametrize(
    ("role", "block"),
    [
        ("user", {"type": "tool_use", "id": "x", "name": "f", "input": {}}),
        ("assistant", {"type": "tool_result", "tool_use_id": "x", "content": "ok"}),
    ],
)
def test_claude_rejects_tool_parts_on_wrong_native_roles(role, block) -> None:
    payload = {"model": "m", "max_tokens": 1, "messages": [{"role": role, "content": [block]}]}
    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\].*role"):
        get_adapter("claude").decode_request(payload)


def test_claude_rejects_tool_parts_on_wrong_canonical_roles() -> None:
    adapter = get_adapter("claude")
    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\].*role"):
        adapter.encode_request(_request(CanonicalMessage("user", (ToolCallPart("x", "f", {}),))))
    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\].*role"):
        adapter.encode_request(
            _request(CanonicalMessage("assistant", (ToolResultPart("x", "f", (TextPart("ok"),)),)))
        )


@pytest.mark.parametrize(
    ("role", "part"),
    [
        ("user", {"functionCall": {"id": "x", "name": "f", "args": {}}}),
        ("model", {"functionResponse": {"id": "x", "name": "f", "response": {"output": "ok"}}}),
    ],
)
def test_gemini_rejects_tool_parts_on_wrong_native_roles(role, part) -> None:
    payload = {"model": "m", "contents": [{"role": role, "parts": [part]}]}
    with pytest.raises(UnsupportedFeatureError, match=r"contents\[0\].*role"):
        get_adapter("gemini").decode_request(payload)


def test_gemini_rejects_tool_parts_on_wrong_canonical_roles() -> None:
    adapter = get_adapter("gemini")
    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\].*role"):
        adapter.encode_request(_request(CanonicalMessage("user", (ToolCallPart("x", "f", {}),))))
    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\].*role"):
        adapter.encode_request(
            _request(CanonicalMessage("assistant", (ToolResultPart("x", "f", (TextPart("ok"),)),)))
        )


def test_openai_rejects_error_tool_results() -> None:
    request = _request(
        CanonicalMessage(
            "user",
            (ToolResultPart("x", "f", (TextPart("failed"),), is_error=True),),
        )
    )
    with pytest.raises(UnsupportedFeatureError, match=r"is_error"):
        get_adapter("openai").encode_request(request)


def test_claude_preserves_tool_result_error_flag() -> None:
    request = _request(
        CanonicalMessage(
            "user",
            (ToolResultPart("x", "f", (TextPart("failed"),), is_error=True),),
        )
    )
    adapter = get_adapter("claude")
    encoded = adapter.encode_request(request)

    assert encoded["messages"][0]["content"][0]["is_error"] is True
    assert adapter.decode_request(encoded) == replace(request, max_output_tokens=4096)


@pytest.mark.parametrize("text", ["123", '"scalar"', '{"x":1}', "plain text"])
def test_gemini_preserves_tool_result_text_exactly_without_json_parsing(text: str) -> None:
    request = _request(CanonicalMessage("user", (ToolResultPart("x", "f", (TextPart(text),)),)))
    adapter = get_adapter("gemini")
    encoded = adapter.encode_request(request)
    response = encoded["contents"][0]["parts"][0]["functionResponse"]["response"]

    assert response == {"output": text}
    assert adapter.decode_request(encoded) == request


def test_gemini_decodes_native_object_result_as_stable_json_text() -> None:
    payload = {
        "model": "m",
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"functionResponse": {"id": "x", "name": "f", "response": {"b": 2, "a": 1}}}
                ],
            }
        ],
    }
    result = get_adapter("gemini").decode_request(payload).messages[0].content[0]
    assert result == ToolResultPart("x", "f", (TextPart('{"a":1,"b":2}'),))


def test_gemini_preserves_explicit_error_result_and_rejects_multiple_content() -> None:
    adapter = get_adapter("gemini")
    request = _request(
        CanonicalMessage(
            "user",
            (ToolResultPart("x", "f", (TextPart("failed"),), is_error=True),),
        )
    )
    encoded = adapter.encode_request(request)

    assert encoded["contents"][0]["parts"][0]["functionResponse"]["response"] == {
        "error": {"message": "failed"}
    }
    assert adapter.decode_request(encoded) == request

    multi = replace(
        request,
        messages=(
            CanonicalMessage(
                "user",
                (ToolResultPart("x", "f", (TextPart("a"), TextPart("b"))),),
            ),
        ),
    )
    with pytest.raises(UnsupportedFeatureError, match=r"content"):
        adapter.encode_request(multi)


def test_gemini_multiple_allowed_function_names_are_preserved_and_not_broadened() -> None:
    payload = {
        "model": "m",
        "contents": [],
        "toolConfig": {
            "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["one", "two"]}
        },
    }
    adapter = get_adapter("gemini")
    request = adapter.decode_request(payload)

    assert request.tool_choice == {"names": ("one", "two")}
    assert adapter.encode_request(request)["toolConfig"] == payload["toolConfig"]
    for protocol in ("openai", "claude"):
        with pytest.raises(UnsupportedFeatureError, match=r"tool_choice\.names"):
            get_adapter(protocol).encode_request(request)


def test_singular_canonical_responses_reject_multiple_native_candidates(load_fixture) -> None:
    openai = load_fixture("openai", "response.json")
    openai["choices"].append(openai["choices"][0])
    with pytest.raises(UnsupportedFeatureError, match="choices"):
        get_adapter("openai").decode_response(openai)

    gemini = load_fixture("gemini", "response.json")
    gemini["candidates"].append(gemini["candidates"][0])
    with pytest.raises(UnsupportedFeatureError, match="candidates"):
        get_adapter("gemini").decode_response(gemini)


@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_native_and_canonical_response_roles_must_be_assistant(protocol, load_fixture) -> None:
    adapter = get_adapter(protocol)
    payload = load_fixture(protocol.value, "response.json")
    if protocol is Protocol.OPENAI:
        payload["choices"][0]["message"]["role"] = "user"
    elif protocol is Protocol.CLAUDE:
        payload["role"] = "user"
    else:
        payload["candidates"][0]["content"]["role"] = "user"
    with pytest.raises(UnsupportedFeatureError, match="role"):
        adapter.decode_response(payload)

    valid = adapter.decode_response(load_fixture(protocol.value, "response.json"))
    invalid = replace(valid, message=replace(valid.message, role="user"))
    with pytest.raises(UnsupportedFeatureError, match="role"):
        adapter.encode_response(invalid)


@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_error_finish_reason_is_never_encoded_as_success(protocol, load_fixture) -> None:
    adapter = get_adapter(protocol)
    response = adapter.decode_response(load_fixture(protocol.value, "response.json"))

    with pytest.raises(UnsupportedFeatureError, match="finish_reason"):
        adapter.encode_response(replace(response, finish_reason="error"))
    with pytest.raises(UnsupportedFeatureError, match="finish_reason"):
        adapter.encode_stream_event(StreamEvent(type="message_end", finish_reason="error"))


@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_native_system_surfaces_reject_non_text_content(protocol) -> None:
    if protocol is Protocol.OPENAI:
        payload = {
            "model": "m",
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "image_url", "image_url": {"url": "https://x"}}],
                }
            ],
        }
    elif protocol is Protocol.CLAUDE:
        payload = {
            "model": "m",
            "max_tokens": 1,
            "system": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": "eA=="},
                }
            ],
            "messages": [],
        }
    else:
        payload = {
            "model": "m",
            "systemInstruction": {
                "parts": [{"inlineData": {"mimeType": "image/png", "data": "eA=="}}]
            },
            "contents": [],
        }

    with pytest.raises(UnsupportedFeatureError, match="system"):
        get_adapter(protocol).decode_request(payload)


@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_canonical_system_rejects_non_text_content(protocol) -> None:
    request = replace(
        _request(CanonicalMessage("user", (TextPart("hi"),))),
        system=(ImagePart(media_type="image/png", data="eA=="),),
    )

    with pytest.raises(UnsupportedFeatureError, match="system"):
        get_adapter(protocol).encode_request(request)


@pytest.mark.parametrize("choice", ["any", "tool", "sometimes", "required_tool"])
def test_openai_rejects_unsupported_string_tool_choice(choice: str) -> None:
    payload = {"model": "m", "messages": [], "tool_choice": choice}
    with pytest.raises(UnsupportedFeatureError, match="tool_choice"):
        get_adapter("openai").decode_request(payload)

    request = replace(
        _request(CanonicalMessage("user", (TextPart("hi"),))),
        tool_choice=choice,
    )
    with pytest.raises(UnsupportedFeatureError, match="tool_choice"):
        get_adapter("openai").encode_request(request)


@pytest.mark.parametrize("protocol", tuple(Protocol))
@pytest.mark.parametrize("bad_tokens", [True, False, -1])
def test_usage_token_counts_are_nonnegative_integers(protocol, bad_tokens, load_fixture) -> None:
    payload = load_fixture(protocol.value, "response.json")
    if protocol is Protocol.OPENAI:
        payload["usage"]["prompt_tokens"] = bad_tokens
    elif protocol is Protocol.CLAUDE:
        payload["usage"]["input_tokens"] = bad_tokens
    else:
        payload["usageMetadata"]["promptTokenCount"] = bad_tokens

    with pytest.raises(UnsupportedFeatureError, match="usage"):
        get_adapter(protocol).decode_response(payload)


@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_canonical_usage_token_counts_are_validated(protocol, load_fixture) -> None:
    adapter = get_adapter(protocol)
    response = replace(
        adapter.decode_response(load_fixture(protocol.value, "response.json")),
        usage=CanonicalUsage(-1, 2),
    )
    with pytest.raises(UnsupportedFeatureError, match="usage"):
        adapter.encode_response(response)

    encoder = adapter.create_stream_encoder()
    with pytest.raises(UnsupportedFeatureError, match="usage"):
        encoder.encode(StreamEvent(type="usage", usage=CanonicalUsage(1, -2)))


@pytest.mark.parametrize(
    "usage",
    [
        CanonicalUsage(1, 2, cache_read_tokens=-1),
        CanonicalUsage(1, 2, cache_write_tokens=-1),
    ],
)
@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_canonical_cache_usage_token_counts_are_validated(
    protocol: Protocol,
    usage: CanonicalUsage,
    load_fixture,
) -> None:
    adapter = get_adapter(protocol)
    response = replace(
        adapter.decode_response(load_fixture(protocol.value, "response.json")),
        usage=usage,
    )

    with pytest.raises(UnsupportedFeatureError, match="usage"):
        adapter.encode_response(response)
