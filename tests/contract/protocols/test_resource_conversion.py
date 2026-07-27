from __future__ import annotations

from dataclasses import replace

import pytest

from ai_gateway.protocols.base import UnsupportedFeatureError
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import (
    CanonicalMessage,
    CanonicalRequest,
    CanonicalResponse,
    ImagePart,
    TextPart,
    ToolResultPart,
)


def _request(*parts: TextPart | ImagePart) -> CanonicalRequest:
    return CanonicalRequest(
        model="model",
        messages=(CanonicalMessage("user", parts),),
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


@pytest.mark.parametrize(
    "part",
    [
        {"inlineData": {"mimeType": "audio/wav", "data": "eA=="}},
        {
            "fileData": {
                "mimeType": "application/pdf",
                "fileUri": "https://example.test/report.pdf",
            }
        },
    ],
)
def test_gemini_non_image_resources_are_not_decoded_as_images(part: dict[str, object]) -> None:
    payload = {"model": "m", "contents": [{"role": "user", "parts": [part]}]}

    with pytest.raises(UnsupportedFeatureError, match=r"mimeType.*image/"):
        get_adapter("gemini").decode_request(payload)


def test_gemini_file_data_requires_media_type_before_canonical_conversion() -> None:
    payload = {
        "model": "m",
        "contents": [
            {
                "role": "user",
                "parts": [{"fileData": {"fileUri": "https://example.test/image.png"}}],
            }
        ],
    }

    with pytest.raises(UnsupportedFeatureError, match=r"mimeType.*required"):
        get_adapter("gemini").decode_request(payload)


def test_gemini_file_image_keeps_media_type_in_canonical_form() -> None:
    payload = {
        "model": "m",
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "fileData": {
                            "mimeType": "image/png",
                            "fileUri": "https://example.test/image.png",
                        }
                    }
                ],
            }
        ],
    }

    part = get_adapter("gemini").decode_request(payload).messages[0].content[0]

    assert part == ImagePart(media_type="image/png", url="https://example.test/image.png")


def test_claude_image_block_rejects_non_image_media_type() -> None:
    payload = {
        "model": "m",
        "max_tokens": 1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": "eA==",
                        },
                    }
                ],
            }
        ],
    }

    with pytest.raises(UnsupportedFeatureError, match=r"media_type.*image/"):
        get_adapter("claude").decode_request(payload)


def test_openai_image_data_url_rejects_non_image_media_type() -> None:
    payload = {
        "model": "m",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:application/pdf;base64,eA=="},
                    }
                ],
            }
        ],
    }

    with pytest.raises(UnsupportedFeatureError, match=r"image_url.url.*image/"):
        get_adapter("openai").decode_request(payload)


@pytest.mark.parametrize("target", ["claude", "gemini"])
def test_openai_image_detail_is_rejected_when_target_cannot_represent_it(target: str) -> None:
    request = _request(ImagePart(url="https://example.test/image.png", detail="high"))

    with pytest.raises(UnsupportedFeatureError, match=r"detail.*not supported"):
        get_adapter(target).encode_request(request)


@pytest.mark.parametrize("media_type", ["application/pdf", "image/svg+xml"])
@pytest.mark.parametrize("target", ["openai", "claude", "gemini"])
def test_canonical_base64_resource_must_have_a_portable_image_media_type(
    target: str,
    media_type: str,
) -> None:
    request = _request(ImagePart(media_type=media_type, data="eA=="))

    with pytest.raises(UnsupportedFeatureError, match=r"media_type.*image/"):
        get_adapter(target).encode_request(request)


@pytest.mark.parametrize("source", ["claude", "gemini"])
def test_non_openai_detail_extension_does_not_become_portable_image_detail(source: str) -> None:
    if source == "claude":
        payload = {
            "model": "m",
            "max_tokens": 1,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "url", "url": "https://example.test/image.png"},
                            "detail": "vendor-value",
                        }
                    ],
                }
            ],
        }
    else:
        payload = {
            "model": "m",
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {
                                "mimeType": "image/png",
                                "fileUri": "https://example.test/image.png",
                            },
                            "detail": "vendor-value",
                        }
                    ],
                }
            ],
        }

    request = get_adapter(source).decode_request(payload)
    image = request.messages[0].content[0]

    assert isinstance(image, ImagePart)
    assert image.detail is None
    encoded_openai = get_adapter("openai").encode_request(replace(request, model="target"))
    assert "detail" not in encoded_openai["messages"][0]["content"][0]["image_url"]


def test_openai_chat_tool_messages_reject_image_content_on_decode() -> None:
    payload = {
        "model": "m",
        "messages": [
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/result.png"},
                    }
                ],
            }
        ],
    }

    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\]\.content.*text"):
        get_adapter("openai").decode_request(payload)


def test_openai_chat_tool_messages_reject_image_content_on_encode() -> None:
    request = replace(
        _request(TextPart("placeholder")),
        messages=(
            CanonicalMessage(
                "user",
                (
                    ToolResultPart(
                        "call_1",
                        "lookup",
                        (ImagePart(media_type="image/png", data="eA=="),),
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(UnsupportedFeatureError, match=r"content.*text"):
        get_adapter("openai").encode_request(request)


def test_openai_chat_assistant_messages_reject_image_content() -> None:
    payload = {
        "model": "m",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/result.png"},
                    }
                ],
            }
        ],
    }

    with pytest.raises(UnsupportedFeatureError, match=r"messages\[0\].*assistant"):
        get_adapter("openai").decode_request(payload)


@pytest.mark.parametrize("decoder", ["chat", "responses"])
def test_openai_image_detail_must_use_an_official_value(decoder: str) -> None:
    if decoder == "chat":
        payload = {
            "model": "m",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://example.test/image.png",
                                "detail": "ultra",
                            },
                        }
                    ],
                }
            ],
        }
        decode = get_adapter("openai").decode_request
    else:
        payload = {
            "model": "m",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": "https://example.test/image.png",
                            "detail": "ultra",
                        }
                    ],
                }
            ],
        }
        decode = get_adapter("openai").decode_responses_request

    with pytest.raises(UnsupportedFeatureError, match=r"detail"):
        decode(payload)


def test_responses_image_data_url_rejects_non_image_media_type() -> None:
    payload = {
        "model": "m",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": "data:application/pdf;base64,eA==",
                    }
                ],
            }
        ],
    }

    with pytest.raises(UnsupportedFeatureError, match=r"image_url.*image/"):
        get_adapter("openai").decode_responses_request(payload)


def test_responses_response_rejects_assistant_image_content() -> None:
    response = CanonicalResponse(
        model="m",
        message=CanonicalMessage(
            "assistant",
            (ImagePart(media_type="image/png", data="eA=="),),
        ),
        finish_reason="stop",
        usage=None,
        metadata={},
    )

    with pytest.raises(UnsupportedFeatureError, match=r"image.*output"):
        get_adapter("openai").encode_responses_api_response(response)
