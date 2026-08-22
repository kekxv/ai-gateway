from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ai_gateway.db.models import ApiKey, Provider, SessionRouteAffinity, User
from ai_gateway.routing.affinity import SessionAffinityStore


async def _records(test_engine: AsyncEngine) -> tuple[int, int, int]:
    suffix = uuid4().hex
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        user = User(email=f"affinity-{suffix}@example.com", password_hash="unused")
        api_key = ApiKey(
            user=user,
            name="affinity",
            key_prefix=f"aff-{suffix}"[:12],
            key_hash=sha256(suffix.encode()).digest(),
        )
        first = Provider(name=f"affinity-first-{suffix}", credential_encrypted=b"first")
        second = Provider(name=f"affinity-second-{suffix}", credential_encrypted=b"second")
        session.add_all((api_key, first, second))
        await session.commit()
        return api_key.id, first.id, second.id


async def test_affinity_store_binds_renews_and_rebinds_provider(
    test_engine: AsyncEngine,
) -> None:
    api_key_id, first_provider_id, second_provider_id = await _records(test_engine)
    now = [datetime(2026, 8, 22, tzinfo=UTC).replace(tzinfo=None)]
    affinity_hash = sha256(b"session").digest()
    async with AsyncSession(test_engine, expire_on_commit=False) as caller:
        store = SessionAffinityStore(
            caller,
            ttl=timedelta(hours=1),
            clock=lambda: now[0],
        )
        assert await store.resolve(api_key_id, affinity_hash) is None
        await store.bind(api_key_id, affinity_hash, first_provider_id)
        assert await store.resolve(api_key_id, affinity_hash) == first_provider_id

        now[0] += timedelta(minutes=30)
        assert await store.resolve(api_key_id, affinity_hash) == first_provider_id

        async with AsyncSession(test_engine) as verify:
            binding = await verify.scalar(select(SessionRouteAffinity))
            assert binding is not None
            assert binding.expires_at == now[0] + timedelta(hours=1)

        await store.bind(api_key_id, affinity_hash, second_provider_id)
        assert await store.resolve(api_key_id, affinity_hash) == second_provider_id


async def test_affinity_store_discards_expired_binding(test_engine: AsyncEngine) -> None:
    api_key_id, provider_id, _ = await _records(test_engine)
    now = [datetime(2026, 8, 22, tzinfo=UTC).replace(tzinfo=None)]
    affinity_hash = sha256(b"expired-session").digest()
    async with AsyncSession(test_engine, expire_on_commit=False) as caller:
        store = SessionAffinityStore(
            caller,
            ttl=timedelta(hours=1),
            clock=lambda: now[0],
        )
        await store.bind(api_key_id, affinity_hash, provider_id)
        now[0] += timedelta(hours=1, seconds=1)

        assert await store.resolve(api_key_id, affinity_hash) is None
