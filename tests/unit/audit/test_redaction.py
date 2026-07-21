from ai_gateway.audit.redaction import REDACTED, redact_headers, redact_json


def test_sensitive_headers_are_removed_case_insensitively() -> None:
    headers = {
        "Authorization": "Bearer secret",
        "PROXY-AUTHORIZATION": "Basic secret",
        "X-Api-Key": "api-key",
        "x-GOOG-api-key": "google-key",
        "Cookie": "session=secret",
        "SET-cookie": "session=secret",
        "Content-Type": "application/json",
        "X-Request-Id": "request-123",
    }

    assert redact_headers(headers) == {
        "Content-Type": "application/json",
        "X-Request-Id": "request-123",
    }


def test_json_credentials_are_redacted_recursively_without_changing_messages() -> None:
    value = {
        "api_key": "top-level-key",
        "messages": [
            {
                "role": "user",
                "content": "The word secret in ordinary message content stays visible.",
                "metadata": {
                    "Access_Token": "nested-token",
                    "safe": "credential is ordinary content here",
                },
            },
            {
                "password": "nested-password",
                "children": [
                    {"refresh_token": "refresh"},
                    {"SECRET": "secret"},
                    {"credential": {"nested": "must not leak"}},
                ],
            },
        ],
    }

    assert redact_json(value) == {
        "api_key": REDACTED,
        "messages": [
            {
                "role": "user",
                "content": "The word secret in ordinary message content stays visible.",
                "metadata": {
                    "Access_Token": REDACTED,
                    "safe": "credential is ordinary content here",
                },
            },
            {
                "password": REDACTED,
                "children": [
                    {"refresh_token": REDACTED},
                    {"SECRET": REDACTED},
                    {"credential": REDACTED},
                ],
            },
        ],
    }
