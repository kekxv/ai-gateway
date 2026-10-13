import pytest

from ai_gateway.core.enums import Protocol
from ai_gateway.gateway.service import InvalidRequestError, _request_payload


@pytest.mark.parametrize("encoding", ["gzip", "br", "zstd", "gzip, deflate"])
@pytest.mark.parametrize("protocol", [Protocol.OPENAI, Protocol.CLAUDE])
def test_compressed_request_is_rejected_before_body_parsing(
    encoding: str, protocol: Protocol
) -> None:
    with pytest.raises(InvalidRequestError, match="Content-Encoding"):
        _request_payload(b'{"model":"m"}', protocol, None, content_encoding=encoding)


@pytest.mark.parametrize("encoding", [None, "", "identity", " Identity "])
def test_uncompressed_request_remains_supported(encoding: str | None) -> None:
    assert _request_payload(b'{"model":"m"}', Protocol.OPENAI, None, content_encoding=encoding) == (
        {"model": "m"},
        "m",
    )
