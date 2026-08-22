from hashlib import sha256

import pytest

from ai_gateway.routing.affinity import client_session_affinity_hash, session_affinity_hash


@pytest.mark.parametrize(
    ("headers", "payload", "identifier"),
    [
        ({"x-claude-code-session-id": "claude-session"}, {}, "claude-session"),
        ({"session-id": "codex-session", "thread-id": "thread"}, {}, "codex-session"),
        ({"thread-id": "codex-thread"}, {}, "codex-thread"),
        ({"x-opencode-session": "opencode-session"}, {}, "opencode-session"),
        ({}, {"prompt_cache_key": "prompt-session"}, "prompt-session"),
        (
            {"x-codex-turn-metadata": '{"session_id":"metadata-session"}'},
            {},
            "metadata-session",
        ),
    ],
)
def test_native_client_session_identifiers_are_hashed(
    headers: dict[str, str],
    payload: dict[str, str],
    identifier: str,
) -> None:
    assert session_affinity_hash(headers, payload) == sha256(f"id:{identifier}".encode()).digest()


def test_explicit_header_wins_over_body_and_prompt_fingerprint() -> None:
    result = session_affinity_hash(
        {"x-claude-code-session-id": "header-session"},
        {
            "prompt_cache_key": "body-session",
            "messages": [{"role": "user", "content": "first prompt"}],
        },
    )

    assert result == sha256(b"id:header-session").digest()


def test_first_user_message_fingerprint_survives_later_turns() -> None:
    first = {
        "messages": [{"role": "user", "content": "fix the failing test"}],
    }
    later = {
        "messages": [
            {"role": "user", "content": "fix the failing test"},
            {"role": "assistant", "content": "I inspected it."},
            {"role": "user", "content": "continue"},
        ],
    }

    assert session_affinity_hash({}, first) == session_affinity_hash({}, later)


def test_request_without_session_or_user_message_has_no_affinity() -> None:
    assert session_affinity_hash({}, {"model": "gpt"}) is None
    assert session_affinity_hash({}, {"messages": []}) is None


def test_client_fingerprint_fallback_is_limited_to_supported_cli_clients() -> None:
    payload = {"messages": [{"role": "user", "content": "first prompt"}]}

    assert client_session_affinity_hash({"user-agent": "python-httpx/0.28"}, payload) is None
    assert client_session_affinity_hash(
        {"user-agent": "pi-coding-agent/0.82.1"}, payload
    ) == session_affinity_hash({}, payload)


def test_native_session_identifier_does_not_require_known_user_agent() -> None:
    assert (
        client_session_affinity_hash({"thread-id": "codex-thread", "user-agent": "unknown"}, {})
        == sha256(b"id:codex-thread").digest()
    )
