from ai_gateway.audit.service import _response_detail


def test_audit_response_headers_describe_stored_decoded_body() -> None:
    detail = _response_detail(
        headers={
            "Content-Encoding": "zstd",
            "Content-Length": "99",
            "Transfer-Encoding": "chunked",
            "Content-Type": "application/json",
            "X-Request-ID": "request-123",
        },
        body=b'{"text":"hello"}',
        metadata={},
    )

    assert detail["headers"] == {
        "Content-Type": "application/json",
        "X-Request-ID": "request-123",
    }
    assert detail["body"] == {"text": "hello"}
