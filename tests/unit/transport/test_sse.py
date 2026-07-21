from __future__ import annotations

import pytest

from ai_gateway.transport.sse import SSEDecoder, SSEEvent


def test_decodes_lf_and_crlf_frames_and_preserves_raw_bytes() -> None:
    decoder = SSEDecoder()

    events = decoder.feed(b"data: one\n\ndata: two\r\n\r\n")

    assert events == [
        SSEEvent(data=b"one", raw=b"data: one\n\n"),
        SSEEvent(data=b"two", raw=b"data: two\r\n\r\n"),
    ]


@pytest.mark.parametrize("split", range(1, len("data: café\n\n".encode())))
def test_event_and_utf8_codepoint_may_be_split_at_every_byte(split: int) -> None:
    wire = "data: café\n\n".encode()
    decoder = SSEDecoder()

    assert decoder.feed(wire[:split]) == []
    assert decoder.feed(wire[split:]) == [SSEEvent(data="café".encode(), raw=wire)]


def test_multiline_data_named_event_and_empty_data() -> None:
    decoder = SSEDecoder()

    events = decoder.feed(
        b"event: content_block_delta\ndata: first\ndata: second\n\nevent: empty\ndata\n\n"
    )

    assert events[0].event == "content_block_delta"
    assert events[0].data == b"first\nsecond"
    assert events[1].event == "empty"
    assert events[1].data == b""


def test_comment_only_frames_are_heartbeats() -> None:
    decoder = SSEDecoder()

    events = decoder.feed(b": keep-alive\n\n: ping\r\n\r\n")

    assert [event.is_heartbeat for event in events] == [True, True]
    assert [event.comment for event in events] == [b"keep-alive", b"ping"]


@pytest.mark.parametrize(
    ("wire", "event_name", "data"),
    [
        (b"data: [DONE]\n\n", None, b"[DONE]"),
        (
            b'event: message_start\ndata: {"type":"message_start"}\n\n',
            "message_start",
            b'{"type":"message_start"}',
        ),
        (
            b'data: {"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}\n\n',
            None,
            b'{"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}',
        ),
    ],
)
def test_protocol_native_frames_are_returned_without_interpretation(
    wire: bytes,
    event_name: str | None,
    data: bytes,
) -> None:
    assert SSEDecoder().feed(wire) == [SSEEvent(data=data, event=event_name, raw=wire)]


def test_ignores_unknown_fields_and_utf8_bom() -> None:
    wire = b"\xef\xbb\xbfignored: value\nid: 7\ndata: ok\n\n"

    assert SSEDecoder().feed(wire) == [SSEEvent(data=b"ok", event_id="7", raw=wire)]
