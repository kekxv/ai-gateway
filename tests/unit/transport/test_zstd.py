from collections.abc import AsyncIterator

import httpx
import pytest

from ai_gateway.core.enums import Protocol
from ai_gateway.transport.sse import GatewayContext, stream_gateway_response


class FragmentedStream(httpx.AsyncByteStream):
    def __init__(self, wire: bytes) -> None:
        self.wire = wire

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for offset in range(0, len(self.wire), 3):
            yield self.wire[offset : offset + 3]


# Fixed zstd fixtures exercise decoding even when the optional decoder is absent.
@pytest.mark.parametrize(
    ("protocol", "endpoint", "wire", "compressed"),
    [
        (
            Protocol.OPENAI,
            "/v1/chat/completions",
            'data: {"choices":[{"delta":{"content":"你好"}}]}\n\ndata: [DONE]\n\n',
            "28b52ffd2042110200646174613a207b2263686f69636573223a5b7b2264656c7461223a7b"
            "22636f6e74656e74223a22e4bda0e5a5bd227d7d5d7d0a0a646174613a205b444f4e455d0a0a",
        ),
        (
            Protocol.CLAUDE,
            "/v1/messages",
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
            '"delta":{"type":"text_delta","text":"你好"}}\n\n'
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
            "28b52ffd20ac750300d205151eb0271d4852aba66094650535740eb2dbccda9096904f526"
            "aac602a33f80877adc93a430e246326dcb5d625b1402c8a624faff8d81e03ab3829414f8"
            "b7562780f06f3992e8f38a1c1b11000baf2d53a0c5eb9e008003f1ca811253c4e05d"
            "370833199aa30acae2f93a832",
        ),
        (
            Protocol.OPENAI,
            "/v1/responses",
            'event: response.output_text.delta\ndata: {"type":"response.output_text.delta",'
            '"delta":"你好"}\n\nevent: response.completed\ndata: {"type":"response.completed",'
            '"response":{"status":"completed"}}\n\n',
            "28b52ffd20c14d0300d245141cc0251dfe5dffaebfb98969b6edb409b909e3d32653713b"
            "a9a4eff47b666bf59ad4f1a9cab5e8f18d640001cc569743c2b0207a6dd15e9d855731"
            "87c76378c4c738c13faef20a194e09ca6481b9271e38070044f78743c1a245d86239c"
            "680bfaa6b44b31514",
        ),
    ],
)
async def test_zstd_sse_is_decoded_before_passthrough(
    protocol: Protocol, endpoint: str, wire: str, compressed: str
) -> None:
    response = httpx.Response(
        200,
        headers={"content-encoding": "zstd", "content-type": "text/event-stream"},
        stream=FragmentedStream(bytes.fromhex(compressed)),
    )
    context = GatewayContext(
        protocol,
        protocol,
        endpoint_path=endpoint,
        openai_operation="responses" if endpoint == "/v1/responses" else "chat_completions",
        native_openai_passthrough=endpoint == "/v1/responses",
    )

    output = b"".join([chunk async for chunk in stream_gateway_response(context, response)])

    assert output == wire.encode()
    assert context.terminal_done_observed
    assert context.audit_preview == wire.encode()
