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
        "proxy": {
            "url": "http://proxy.internal:8080",
            "auth": {"headers": {"X-Proxy-Token": "must-not-leak"}},
        },
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
        "proxy": REDACTED,
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


def test_json_credential_key_normalization_covers_case_hyphen_and_nested_sequences() -> None:
    value = {
        "apiKey": "api-key",
        "API-KEY": "api-key-2",
        "accessToken": "access-token",
        "refresh-token": "refresh-token",
        "clientSecret": "client-secret",
        "auth-token": "auth-token",
        "privateKey": "private-key",
        "credentials": {"password": "nested-password"},
        "items": [{"CLIENT-SECRET": "list-secret"}],
        "model": "gpt-4o",
        "max_tokens": 128,
        "token_count": 3,
        "message": "token appears in ordinary content",
    }

    assert redact_json(value) == {
        "apiKey": REDACTED,
        "API-KEY": REDACTED,
        "accessToken": REDACTED,
        "refresh-token": REDACTED,
        "clientSecret": REDACTED,
        "auth-token": REDACTED,
        "privateKey": REDACTED,
        "credentials": REDACTED,
        "items": [{"CLIENT-SECRET": REDACTED}],
        "model": "gpt-4o",
        "max_tokens": 128,
        "token_count": 3,
        "message": "token appears in ordinary content",
    }
