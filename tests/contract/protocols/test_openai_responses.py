from __future__ import annotations

import pytest

from ai_gateway.protocols.base import UnsupportedFeatureError, decode_sse
from ai_gateway.protocols.openai import OpenAIAdapter, _ResponsesAPIStreamEncoder
from ai_gateway.protocols.types import (
    CanonicalMessage,
    CanonicalResponse,
    CanonicalUsage,
    ImagePart,
    StreamEvent,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)


def test_responses_request_decodes_official_portable_shape() -> None:
    request = OpenAIAdapter().decode_responses_request(
        {
            "model": "gpt-5.6",
            "instructions": "Be concise.",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Describe this image"},
                        {
                            "type": "input_image",
                            "image_url": "https://example.test/image.png",
                            "detail": "high",
                        },
                    ],
                },
                {
                    "type": "function_call",
                    "id": "fc_123",
                    "call_id": "call_123",
                    "name": "lookup",
                    "arguments": '{"id":7}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": '{"name":"record"}',
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "lookup",
                    "description": "Look up a record",
                    "parameters": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                        "required": ["id"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            ],
            "tool_choice": {"type": "function", "name": "lookup"},
            "temperature": 0.2,
            "top_p": 0.8,
            "max_output_tokens": 64,
            "stream": True,
        }
    )

    assert request.system == (TextPart("Be concise."),)
    assert request.max_output_tokens == 64
    assert request.tool_choice == {"name": "lookup"}
    assert request.tools[0].name == "lookup"
    assert request.tools[0].input_schema["required"] == ("id",)
    assert isinstance(request.messages[0].content[0], TextPart)
    assert request.messages[0].content[0].text == "Describe this image"
    assert isinstance(request.messages[0].content[1], ImagePart)
    assert request.messages[0].content[1].url == "https://example.test/image.png"
    assert request.messages[0].content[1].detail == "high"
    assert isinstance(request.messages[1].content[0], ToolCallPart)
    assert request.messages[1].content[0].id == "call_123"
    assert isinstance(request.messages[2].content[0], ToolResultPart)
    assert request.messages[2].content[0].tool_call_id == "call_123"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("previous_response_id", "resp_previous"),
        ("conversation", "conv_123"),
        ("background", True),
        ("tools", [{"type": "web_search"}]),
    ],
)
def test_responses_portable_fallback_rejects_stateful_and_builtin_features(
    field: str,
    value: object,
) -> None:
    payload: dict[str, object] = {"model": "gpt-5.6", "input": "hello", field: value}

    with pytest.raises(UnsupportedFeatureError, match=field):
        OpenAIAdapter().decode_responses_request(payload)


def test_responses_response_marks_token_limit_as_incomplete() -> None:
    encoded = OpenAIAdapter().encode_responses_api_response(
        CanonicalResponse(
            model="gpt-5.6",
            message=CanonicalMessage(role="assistant", content=(TextPart("partial"),)),
            finish_reason="length",
            usage=CanonicalUsage(10, 4),
            metadata={"response_id": "resp_test", "created": 123},
        )
    )

    assert encoded["status"] == "incomplete"
    assert encoded["incomplete_details"] == {"reason": "max_output_tokens"}
    assert encoded["error"] is None
    assert encoded["parallel_tool_calls"] is True
    assert encoded["tool_choice"] == "auto"
    assert encoded["tools"] == []
    assert encoded["usage"] == {
        "input_tokens": 10,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": 4,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 14,
    }


def _payloads(frames: tuple[bytes, ...]) -> list[dict[str, object]]:
    return [decode_sse(frame)[1] for frame in frames]


def test_responses_stream_event_name_matches_payload_type() -> None:
    frames = _ResponsesAPIStreamEncoder().encode(
        StreamEvent(type="message_start", role="assistant", model="gpt-5.6")
    )

    assert [decode_sse(frame)[0] for frame in frames] == [
        "response.created",
        "response.in_progress",
    ]


def test_responses_stream_emits_stateful_official_text_events() -> None:
    encoder = _ResponsesAPIStreamEncoder()
    payloads: list[dict[str, object]] = []
    for event in (
        StreamEvent(type="message_start", role="assistant", model="gpt-5.6"),
        StreamEvent(type="content_delta", text="Hello ", model="gpt-5.6"),
        StreamEvent(type="content_delta", text="world", model="gpt-5.6"),
        StreamEvent(type="message_end", finish_reason="stop", model="gpt-5.6"),
        StreamEvent(type="usage", usage=CanonicalUsage(5, 2), model="gpt-5.6"),
        StreamEvent(type="done", model="gpt-5.6"),
    ):
        payloads.extend(_payloads(encoder.encode(event)))

    assert [payload["sequence_number"] for payload in payloads] == list(
        range(len(payloads))
    )
    event_types = [payload["type"] for payload in payloads]
    assert event_types == [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]
    deltas = [payload for payload in payloads if payload["type"] == "response.output_text.delta"]
    assert [payload["delta"] for payload in deltas] == ["Hello ", "world"]
    assert all("response_id" in payload and "item_id" in payload for payload in deltas)
    text_done = next(
        payload for payload in payloads if payload["type"] == "response.output_text.done"
    )
    assert text_done["text"] == "Hello world"
    completed = payloads[-1]["response"]
    assert completed["status"] == "completed"
    assert completed["output"][0]["content"][0]["text"] == "Hello world"
    assert completed["usage"]["total_tokens"] == 7


def test_responses_stream_tracks_multiple_function_calls_independently() -> None:
    encoder = _ResponsesAPIStreamEncoder()
    payloads: list[dict[str, object]] = []
    for event in (
        StreamEvent(type="message_start", role="assistant", model="gpt-5.6"),
        StreamEvent(
            type="tool_call_delta",
            index=0,
            tool_index=0,
            tool_call_id="call_one",
            tool_name="first",
            arguments_delta='{"a":',
        ),
        StreamEvent(
            type="tool_call_delta",
            index=0,
            tool_index=0,
            tool_call_id="call_one",
            arguments_delta="1}",
        ),
        StreamEvent(
            type="tool_call_delta",
            index=1,
            tool_index=1,
            tool_call_id="call_two",
            tool_name="second",
            arguments_delta='{"b":2}',
        ),
        StreamEvent(type="message_end", finish_reason="tool_call", model="gpt-5.6"),
        StreamEvent(type="done", model="gpt-5.6"),
    ):
        payloads.extend(_payloads(encoder.encode(event)))

    added = [payload for payload in payloads if payload["type"] == "response.output_item.added"]
    assert [(payload["output_index"], payload["item"]["call_id"]) for payload in added] == [
        (0, "call_one"),
        (1, "call_two"),
    ]
    done = [
        payload
        for payload in payloads
        if payload["type"] == "response.function_call_arguments.done"
    ]
    assert [(payload["item_id"], payload["arguments"]) for payload in done] == [
        (added[0]["item"]["id"], '{"a":1}'),
        (added[1]["item"]["id"], '{"b":2}'),
    ]
    completed_output = payloads[-1]["response"]["output"]
    assert [item["name"] for item in completed_output] == ["first", "second"]
    assert [item["arguments"] for item in completed_output] == ['{"a":1}', '{"b":2}']


def test_responses_stream_uses_incomplete_terminal_event_for_output_limit() -> None:
    encoder = _ResponsesAPIStreamEncoder()
    payloads: list[dict[str, object]] = []
    for event in (
        StreamEvent(type="message_start", role="assistant", model="gpt-5.6"),
        StreamEvent(type="content_delta", text="partial", model="gpt-5.6"),
        StreamEvent(type="message_end", finish_reason="length", model="gpt-5.6"),
        StreamEvent(type="done", model="gpt-5.6"),
    ):
        payloads.extend(_payloads(encoder.encode(event)))

    assert payloads[-1]["type"] == "response.incomplete"
    assert payloads[-1]["response"]["status"] == "incomplete"
    assert payloads[-1]["response"]["incomplete_details"] == {
        "reason": "max_output_tokens"
    }
