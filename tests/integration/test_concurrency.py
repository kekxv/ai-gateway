from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from importlib import import_module
from uuid import uuid4

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from ai_gateway.admin.api_keys import rotate_api_key
from ai_gateway.admin.model_sync import sync_provider_models
from ai_gateway.billing.service import BillingService
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol, RouteRuntimeState, RouteSource
from ai_gateway.core.security import encrypt_secret, hash_password
from ai_gateway.db.models import (
    Account,
    ApiKey,
    LedgerEntry,
    Model,
    ModelRoute,
    Provider,
    ProviderProtocol,
    User,
)
from ai_gateway.protocols.types import CanonicalUsage
from ai_gateway.routing.service import Router


class _HttpClientFactory:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def client_for(self, _: str | httpx.URL) -> httpx.AsyncClient:
        return self.client


async def test_concurrent_first_registrations_create_exactly_one_admin(
    test_engine: AsyncEngine,
) -> None:
    auth_service = import_module("ai_gateway.auth.service")
    register_user = getattr(auth_service, "register_user", None)
    assert callable(register_user), "auth.service.register_user must be implemented"

    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    suffix = uuid4().hex
    emails = [
        f"first-registration-a-{suffix}@example.com",
        f"first-registration-b-{suffix}@example.com",
    ]

    async def register_once(email: str) -> User:
        async with sessions() as session:
            return await register_user(
                session=session,
                email=email,
                password="concurrent-registration-password",
            )

    user_ids: list[int] = []
    try:
        first, second = await asyncio.gather(*(register_once(email) for email in emails))
        user_ids = [first.id, second.id]

        async with sessions() as check:
            users = list(
                await check.scalars(
                    select(User).where(User.id.in_(user_ids)).options(joinedload(User.account))
                )
            )

        assert len(users) == 2
        assert {user.email for user in users} == set(emails)
        assert sorted(user.role for user in users) == ["admin", "user"]
        assert all(user.account is not None for user in users)
    finally:
        if user_ids:
            async with sessions() as cleanup:
                users = await cleanup.scalars(select(User).where(User.id.in_(user_ids)))
                for user in users:
                    await cleanup.delete(user)
                await cleanup.commit()


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="concurrency-test-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )


async def test_concurrent_model_sync_creates_no_duplicate_discovered_routes(
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_gateway.admin import model_sync as model_sync_module

    settings = _settings()
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    suffix = uuid4().hex
    model_name = f"concurrency-model-{suffix}"
    provider = Provider(
        name=f"concurrency-provider-{suffix}",
        credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
        protocols=[
            ProviderProtocol(
                protocol=Protocol.OPENAI,
                base_url="https://provider.invalid/v1",
            )
        ],
    )
    async with sessions() as setup:
        setup.add(provider)
        await setup.commit()
        provider_id = provider.id

    original_lookup = model_sync_module._models_by_discovered_name
    entered = 0
    lock = asyncio.Lock()
    ready = asyncio.Event()

    async def synchronized_lookup(
        session: AsyncSession,
        names: set[str],
    ) -> dict[str, Model]:
        nonlocal entered
        result = await original_lookup(session, names)
        async with lock:
            entered += 1
            if entered == 2:
                ready.set()
        if entered <= 2:
            await asyncio.wait_for(ready.wait(), timeout=2)
        return result

    monkeypatch.setattr(model_sync_module, "_models_by_discovered_name", synchronized_lookup)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": model_name}, {"id": model_name}], "has_more": False},
            request=request,
        )

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            factory = _HttpClientFactory(client)
            async with sessions() as first, sessions() as second:
                await asyncio.gather(
                    sync_provider_models(
                        provider_id,
                        session=first,
                        http_client_factory=factory,
                        settings=settings,
                    ),
                    sync_provider_models(
                        provider_id,
                        session=second,
                        http_client_factory=factory,
                        settings=settings,
                    ),
                )

        async with sessions() as check:
            models = list(
                await check.scalars(select(Model).where(Model.canonical_name == model_name))
            )
            routes = list(
                await check.scalars(select(ModelRoute).where(ModelRoute.provider_id == provider_id))
            )
        assert len(models) == 1
        assert len(routes) == 1
        assert routes[0].model_id == models[0].id
        assert routes[0].source is RouteSource.DISCOVERED
    finally:
        async with sessions() as cleanup:
            await cleanup.execute(delete(ModelRoute).where(ModelRoute.provider_id == provider_id))
            await cleanup.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id == provider_id)
            )
            await cleanup.execute(delete(Provider).where(Provider.id == provider_id))
            await cleanup.execute(delete(Model).where(Model.canonical_name == model_name))
            await cleanup.commit()


async def test_concurrent_half_open_claims_allow_one_probe(test_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    suffix = uuid4().hex
    now = datetime.now(UTC).replace(tzinfo=None)
    provider = Provider(
        name=f"claim-provider-{suffix}",
        credential_encrypted=b"encrypted",
    )
    route = ModelRoute(
        model=Model(canonical_name=f"claim-model-{suffix}", display_name="Claim model"),
        provider=provider,
        provider_protocol=ProviderProtocol(
            provider=provider,
            protocol=Protocol.OPENAI,
            base_url="https://claim.invalid/v1",
        ),
        upstream_model="claim-upstream",
        runtime_state=RouteRuntimeState.OPEN,
        consecutive_failures=3,
        disabled_until=now - timedelta(seconds=1),
    )
    async with sessions() as setup:
        setup.add(route)
        await setup.commit()
        route_id = route.id
        model_id = route.model_id
        provider_id = route.provider_id

    async def claim_once() -> bool:
        async with sessions() as session:
            return await Router(session, mutation_session_factory=sessions)._claim_half_open(
                route_id,
                now,
            )

    try:
        assert sum(await asyncio.gather(claim_once(), claim_once())) == 1
        async with sessions() as check:
            stored = await check.get(ModelRoute, route_id)
            assert stored is not None
            assert stored.runtime_state is RouteRuntimeState.HALF_OPEN
    finally:
        async with sessions() as cleanup:
            await cleanup.execute(delete(ModelRoute).where(ModelRoute.id == route_id))
            await cleanup.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id == provider_id)
            )
            await cleanup.execute(delete(Provider).where(Provider.id == provider_id))
            await cleanup.execute(delete(Model).where(Model.id == model_id))
            await cleanup.commit()


async def test_concurrent_settlement_is_idempotent_and_balance_never_negative(
    test_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    service = BillingService(sessions)
    suffix = uuid4().hex
    model = Model(
        canonical_name=f"settlement-model-{suffix}",
        display_name="Settlement model",
        input_price_per_million=Decimal("100000.00000000"),
        output_price_per_million=Decimal("100000.00000000"),
    )
    user = User(
        email=f"settlement-{suffix}@example.com",
        password_hash=hash_password("settlement-password"),
        account=Account(balance=Decimal("1.00000000")),
    )
    async with sessions() as setup:
        setup.add_all([model, user])
        await setup.commit()
        user_id = user.id
        account_id = user.account.id
        model_id = model.id

    reservation = await service.reserve_balance(
        user_id=user_id,
        model=model,
        estimated_input_tokens=1,
        max_output_tokens=1,
        request_id=str(uuid4()),
        idempotency_key=f"reserve-{suffix}",
    )
    settlement_key = f"settle-{suffix}"

    async def settle_once():
        return await service.settle_request(
            reservation_id=reservation.ledger_entry_id,
            model=model,
            usage=CanonicalUsage(1, 1),
            idempotency_key=settlement_key,
        )

    try:
        first, second = await asyncio.gather(settle_once(), settle_once())
        assert first == second
        async with sessions() as check:
            account = await check.get(Account, account_id)
            assert account is not None
            entry_count = await check.scalar(
                select(func.count())
                .select_from(LedgerEntry)
                .where(LedgerEntry.account_id == account_id)
            )
            key_count = await check.scalar(
                select(func.count(func.distinct(LedgerEntry.idempotency_key))).where(
                    LedgerEntry.account_id == account_id
                )
            )
            assert account.balance == Decimal("0.80000000")
            assert account.balance >= 0
            assert entry_count == key_count == 3
    finally:
        async with sessions() as cleanup:
            cleanup_user = await cleanup.get(User, user_id)
            if cleanup_user is not None:
                await cleanup.delete(cleanup_user)
            await cleanup.execute(delete(Model).where(Model.id == model_id))
            await cleanup.commit()


async def test_concurrent_api_key_rotation_creates_one_replacement(
    test_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    suffix = uuid4().hex
    user = User(
        email=f"rotation-{suffix}@example.com",
        password_hash=hash_password("rotation-password"),
        account=Account(),
    )
    old_key = ApiKey(
        user=user,
        name="concurrent rotation",
        key_prefix="sk-gw-oldkey",
        key_hash=sha256(f"old-key-{suffix}".encode()).digest(),
        scope=ApiKeyScope.ALL,
        is_active=True,
    )
    async with sessions() as setup:
        setup.add(old_key)
        await setup.commit()
        old_key_id = old_key.id
        user_id = user.id

    async def rotate_once() -> object:
        async with sessions() as session:
            try:
                return await rotate_api_key(old_key_id, session, user)
            except HTTPException as exc:
                return exc

    try:
        results = await asyncio.gather(rotate_once(), rotate_once())
        assert sum(not isinstance(result, HTTPException) for result in results) == 1
        assert (
            sum(
                isinstance(result, HTTPException) and result.status_code == 409
                for result in results
            )
            == 1
        )
        async with sessions() as check:
            keys = list(await check.scalars(select(ApiKey).where(ApiKey.user_id == user_id)))
        assert len(keys) == 2
        assert sum(key.is_active for key in keys) == 1
        assert sum(key.id != old_key_id for key in keys) == 1
    finally:
        async with sessions() as cleanup:
            cleanup_user = await cleanup.get(User, user_id)
            if cleanup_user is not None:
                await cleanup.delete(cleanup_user)
                await cleanup.commit()
