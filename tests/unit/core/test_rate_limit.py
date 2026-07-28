from fastapi import Request

from ai_gateway.core import rate_limit


def test_client_ip_ignores_untrusted_forwarding_header() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/auth/login",
            "raw_path": b"/auth/login",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"198.51.100.9")],
            "client": ("203.0.113.4", 1234),
            "server": ("test", 80),
        }
    )

    assert hasattr(rate_limit, "client_ip")
    assert rate_limit.client_ip(request) == "203.0.113.4"
