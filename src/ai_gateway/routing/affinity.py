from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import orjson
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.db.models import SessionRouteAffinity
from ai_gateway.routing.sessions import MutationSessionFactory, mutation_session_factory_for

_SESSION_HEADERS = (
    "x-claude-code-session-id",
    "session-id",
    "thread-id",
    "x-opencode-session",
)
_SESSION_BODY_FIELDS = ("prompt_cache_key", "conversation")
_SUPPORTED_CLIENT_MARKERS = ("claude", "codex", "opencode", "pi-coding-agent")
Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SessionAffinityStore:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ttl: timedelta = timedelta(hours=1),
        clock: Clock = _utcnow,
        mutation_session_factory: MutationSessionFactory | None = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        self._ttl = ttl
        self._clock = clock
        self._mutation_session_factory = (
            mutation_session_factory
            if mutation_session_factory is not None
            else mutation_session_factory_for(session)
        )

    async def resolve(self, api_key_id: int, affinity_hash: bytes) -> int | None:
        now = self._clock()
        async with self._mutation_session_factory() as mutation_session:
            async with mutation_session.begin():
                binding = await mutation_session.scalar(
                    select(SessionRouteAffinity)
                    .where(
                        SessionRouteAffinity.api_key_id == api_key_id,
                        SessionRouteAffinity.affinity_hash == affinity_hash,
                    )
                    .with_for_update()
                )
                if binding is None:
                    return None
                if binding.expires_at <= now:
                    await mutation_session.delete(binding)
                    return None
                binding.expires_at = now + self._ttl
                binding.updated_at = now
                return binding.provider_id

    async def bind(self, api_key_id: int, affinity_hash: bytes, provider_id: int) -> None:
        now = self._clock()
        async with self._mutation_session_factory() as mutation_session:
            async with mutation_session.begin():
                statement = insert(SessionRouteAffinity).values(
                    api_key_id=api_key_id,
                    affinity_hash=affinity_hash,
                    provider_id=provider_id,
                    expires_at=now + self._ttl,
                    updated_at=now,
                )
                await mutation_session.execute(
                    statement.on_duplicate_key_update(
                        provider_id=provider_id,
                        expires_at=now + self._ttl,
                        updated_at=now,
                    )
                )


def session_affinity_hash(
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
) -> bytes | None:
    identifier = _native_session_identifier(headers, payload)
    if identifier is not None:
        return sha256(f"id:{identifier}".encode()).digest()

    first_user_message = _first_user_message(payload)
    if first_user_message is None:
        return None
    serialized = orjson.dumps(first_user_message, option=orjson.OPT_SORT_KEYS)
    return sha256(b"prompt:" + serialized).digest()


def client_session_affinity_hash(
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
) -> bytes | None:
    identifier = _native_session_identifier(headers, payload)
    if identifier is not None:
        return sha256(f"id:{identifier}".encode()).digest()

    user_agent = headers.get("user-agent", "").lower()
    originator = headers.get("originator", "").lower()
    known_client = any(
        marker in user_agent or marker in originator for marker in _SUPPORTED_CLIENT_MARKERS
    ) or user_agent.startswith("pi/")
    if not known_client:
        return None

    first_user_message = _first_user_message(payload)
    if first_user_message is None:
        return None
    serialized = orjson.dumps(first_user_message, option=orjson.OPT_SORT_KEYS)
    return sha256(b"prompt:" + serialized).digest()


def _native_session_identifier(
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
) -> str | None:
    for name in _SESSION_HEADERS:
        if identifier := _normalized_identifier(headers.get(name)):
            return identifier

    for name in _SESSION_BODY_FIELDS:
        if identifier := _normalized_identifier(payload.get(name)):
            return identifier

    metadata = headers.get("x-codex-turn-metadata")
    if metadata is None:
        return None
    try:
        parsed = orjson.loads(metadata)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return _normalized_identifier(parsed.get("session_id")) or _normalized_identifier(
        parsed.get("thread_id")
    )


def _normalized_identifier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 512:
        return None
    return normalized


def _first_user_message(payload: Mapping[str, Any]) -> object | None:
    for field in ("messages", "input", "contents"):
        items = payload.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("role") == "user":
                return item
    return None
