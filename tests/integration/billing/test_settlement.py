from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ai_gateway.billing.service import (
    InsufficientBalance,
    SettlementResult,
    reserve_balance,
    settle_request,
)
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import LedgerKind, UsageSource
from ai_gateway.core.security import hash_password, issue_access_token
from ai_gateway.db.models import Account, LedgerEntry, Model, User
from ai_gateway.main import create_app
from ai_gateway.protocols.types import CanonicalUsage


@pytest_asyncio.fixture
async def billing_user(test_engine: AsyncEngine) -> AsyncIterator[User]:
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        user = User(
            email=f"billing-{uuid4().hex}@example.com",
            password_hash=hash_password("billing-password"),
            role="user",
        )
        user.account = Account(balance=Decimal("1.00000000"))
        setup.add(user)
        await setup.commit()
        user_id = user.id
    yield user
    await _delete_user(test_engine, user_id)


@pytest_asyncio.fixture
async def admin_user_record(test_engine: AsyncEngine) -> AsyncIterator[User]:
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        user = User(
            email=f"billing-admin-{uuid4().hex}@example.com",
            password_hash=hash_password("admin-password"),
            role="admin",
        )
        user.account = Account()
        setup.add(user)
        await setup.commit()
        user_id = user.id
    yield user
    await _delete_user(test_engine, user_id)


@pytest_asyncio.fixture
async def regular_user_record(test_engine: AsyncEngine) -> AsyncIterator[User]:
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        user = User(
            email=f"billing-member-{uuid4().hex}@example.com",
            password_hash=hash_password("member-password"),
            role="user",
        )
        user.account = Account()
        setup.add(user)
        await setup.commit()
        user_id = user.id
    yield user
    await _delete_user(test_engine, user_id)


@pytest.fixture
def billing_settings(test_engine: AsyncEngine) -> Settings:
    return Settings(
        environment="test",
        database_url=test_engine.url.render_as_string(hide_password=False),
        jwt_secret="billing-integration-test-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )


async def _client_for_user(
    *,
    settings: Settings,
    user: User,
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    token = issue_access_token(user_id=user.id, settings=settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client
    await app.state.engine.dispose()


@pytest_asyncio.fixture
async def admin_client(
    billing_settings: Settings,
    admin_user_record: User,
) -> AsyncIterator[AsyncClient]:
    async for client in _client_for_user(
        settings=billing_settings,
        user=admin_user_record,
    ):
        yield client


@pytest_asyncio.fixture
async def non_admin_client(
    billing_settings: Settings,
    regular_user_record: User,
) -> AsyncIterator[AsyncClient]:
    async for client in _client_for_user(
        settings=billing_settings,
        user=regular_user_record,
    ):
        yield client


@pytest.fixture
def priced_model() -> Model:
    return Model(
        canonical_name="billing-model",
        display_name="Billing model",
        input_price_per_million=Decimal("100000.00000000"),
        output_price_per_million=Decimal("100000.00000000"),
    )


async def _delete_user(test_engine: AsyncEngine, user_id: int) -> None:
    async with AsyncSession(test_engine) as cleanup:
        user = await cleanup.get(User, user_id)
        if user is not None:
            await cleanup.delete(user)
            await cleanup.commit()


async def _set_balance(test_engine: AsyncEngine, account_id: int, amount: Decimal) -> None:
    async with AsyncSession(test_engine) as mutation:
        account = await mutation.get(Account, account_id)
        assert account is not None
        account.balance = amount
        await mutation.commit()


async def test_reservation_and_settlement_update_balance_spend_and_ledger_atomically(
    session: AsyncSession,
    billing_user: User,
    priced_model: Model,
) -> None:
    reservation = await reserve_balance(
        session,
        user_id=billing_user.id,
        model=priced_model,
        estimated_input_tokens=1,
        max_output_tokens=None,
        default_max_output_tokens=2,
        request_id=str(uuid4()),
        idempotency_key=f"reserve-{uuid4().hex}",
    )
    assert reservation.amount == Decimal("0.30000000")
    assert reservation.balance_after == Decimal("0.70000000")

    result = await settle_request(
        session,
        reservation_id=reservation.ledger_entry_id,
        model=priced_model,
        usage=CanonicalUsage(1, 1),
        usage_source=UsageSource.PROVIDER,
        idempotency_key=f"settle-{uuid4().hex}",
    )

    assert result.charged_amount == Decimal("0.20000000")
    assert result.balance == Decimal("0.80000000")
    assert result.total_spent == Decimal("0.20000000")
    entries = (
        await session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.account_id == billing_user.account.id)
            .order_by(LedgerEntry.id)
        )
    ).all()
    assert [(entry.kind, entry.amount, entry.balance_after) for entry in entries] == [
        (LedgerKind.RESERVATION, Decimal("-0.30000000"), Decimal("0.70000000")),
        (
            LedgerKind.RESERVATION_RELEASE,
            Decimal("0.30000000"),
            Decimal("1.00000000"),
        ),
        (LedgerKind.USAGE, Decimal("-0.20000000"), Decimal("0.80000000")),
    ]


async def test_insufficient_balance_fails_before_any_upstream_work(
    session: AsyncSession,
    test_engine: AsyncEngine,
    billing_user: User,
    priced_model: Model,
) -> None:
    await _set_balance(test_engine, billing_user.account.id, Decimal("0.29000000"))
    upstream_started = False

    with pytest.raises(InsufficientBalance) as raised:
        await reserve_balance(
            session,
            user_id=billing_user.id,
            model=priced_model,
            estimated_input_tokens=1,
            max_output_tokens=2,
            request_id=str(uuid4()),
            idempotency_key=f"reserve-{uuid4().hex}",
        )
        upstream_started = True

    assert raised.value.status_code == 402
    assert raised.value.code == "insufficient_balance"
    assert upstream_started is False
    assert (
        await session.scalar(
            select(LedgerEntry.id).where(LedgerEntry.account_id == billing_user.account.id)
        )
        is None
    )


async def test_exact_zero_balance_is_allowed_and_later_requests_fail(
    session: AsyncSession,
    test_engine: AsyncEngine,
    billing_user: User,
    priced_model: Model,
) -> None:
    await _set_balance(test_engine, billing_user.account.id, Decimal("0.30000000"))

    reservation = await reserve_balance(
        session,
        user_id=billing_user.id,
        model=priced_model,
        estimated_input_tokens=1,
        max_output_tokens=2,
        request_id=str(uuid4()),
        idempotency_key=f"reserve-{uuid4().hex}",
    )

    assert reservation.balance_after == Decimal("0.00000000")
    with pytest.raises(InsufficientBalance):
        await reserve_balance(
            session,
            user_id=billing_user.id,
            model=priced_model,
            estimated_input_tokens=0,
            max_output_tokens=1,
            request_id=str(uuid4()),
            idempotency_key=f"reserve-{uuid4().hex}",
        )


async def test_actual_charge_above_reservation_exhausts_without_negative_balance(
    session: AsyncSession,
    test_engine: AsyncEngine,
    billing_user: User,
    priced_model: Model,
) -> None:
    await _set_balance(test_engine, billing_user.account.id, Decimal("0.50000000"))
    reservation = await reserve_balance(
        session,
        user_id=billing_user.id,
        model=priced_model,
        estimated_input_tokens=1,
        max_output_tokens=1,
        request_id=str(uuid4()),
        idempotency_key=f"reserve-{uuid4().hex}",
    )

    result = await settle_request(
        session,
        reservation_id=reservation.ledger_entry_id,
        model=priced_model,
        usage=CanonicalUsage(4, 4),
        usage_source=UsageSource.ESTIMATED,
        idempotency_key=f"settle-{uuid4().hex}",
    )

    assert result.actual_cost == Decimal("0.80000000")
    assert result.charged_amount == Decimal("0.50000000")
    assert result.balance == Decimal("0.00000000")
    assert result.exhausted is True


async def test_duplicate_settlement_is_idempotent(
    session: AsyncSession,
    billing_user: User,
    priced_model: Model,
) -> None:
    reservation = await reserve_balance(
        session,
        user_id=billing_user.id,
        model=priced_model,
        estimated_input_tokens=1,
        max_output_tokens=1,
        request_id=str(uuid4()),
        idempotency_key=f"reserve-{uuid4().hex}",
    )
    settlement_key = f"settle-{uuid4().hex}"
    first = await settle_request(
        session,
        reservation_id=reservation.ledger_entry_id,
        model=priced_model,
        usage=CanonicalUsage(1, 1),
        idempotency_key=settlement_key,
    )
    second = await settle_request(
        session,
        reservation_id=reservation.ledger_entry_id,
        model=priced_model,
        usage=CanonicalUsage(1, 1),
        idempotency_key=settlement_key,
    )

    assert second == first
    assert await session.scalar(
        select(Account.total_spent).where(Account.id == reservation.account_id)
    ) == Decimal("0.20000000")
    assert (
        len(
            (
                await session.scalars(
                    select(LedgerEntry).where(LedgerEntry.account_id == reservation.account_id)
                )
            ).all()
        )
        == 3
    )


async def test_concurrent_duplicate_settlement_applies_one_usage_charge(
    test_engine: AsyncEngine,
    priced_model: Model,
) -> None:
    suffix = uuid4().hex
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        user = User(
            email=f"duplicate-settlement-{suffix}@example.com",
            password_hash=hash_password("billing-password"),
        )
        user.account = Account(balance=Decimal("1.00000000"))
        setup.add(user)
        await setup.commit()
        user_id = user.id
        account_id = user.account.id
        reservation = await reserve_balance(
            setup,
            user_id=user_id,
            model=priced_model,
            estimated_input_tokens=1,
            max_output_tokens=1,
            request_id=str(uuid4()),
            idempotency_key=f"duplicate-reserve-{suffix}",
        )
        reservation_id = reservation.ledger_entry_id

    ready = asyncio.Event()
    entered = 0
    entered_lock = asyncio.Lock()
    settlement_key = f"duplicate-settle-{suffix}"

    async def settle_once() -> SettlementResult:
        nonlocal entered
        async with AsyncSession(test_engine, expire_on_commit=False) as settlement_session:
            async with entered_lock:
                entered += 1
                if entered == 2:
                    ready.set()
            await ready.wait()
            return await settle_request(
                settlement_session,
                reservation_id=reservation_id,
                model=priced_model,
                usage=CanonicalUsage(1, 1),
                idempotency_key=settlement_key,
            )

    try:
        first, second = await asyncio.gather(settle_once(), settle_once())
        assert second == first
        async with AsyncSession(test_engine, expire_on_commit=False) as check:
            account = await check.get(Account, account_id)
            assert account is not None
            assert account.balance == Decimal("0.80000000")
            assert account.total_spent == Decimal("0.20000000")
            entries = (
                await check.scalars(select(LedgerEntry).where(LedgerEntry.account_id == account_id))
            ).all()
            assert len(entries) == 3
    finally:
        async with AsyncSession(test_engine) as cleanup:
            cleanup_user = await cleanup.get(User, user_id)
            if cleanup_user is not None:
                await cleanup.delete(cleanup_user)
                await cleanup.commit()


async def test_two_concurrent_charges_never_make_balance_negative(
    test_engine: AsyncEngine,
    priced_model: Model,
) -> None:
    suffix = uuid4().hex
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        user = User(
            email=f"concurrent-billing-{suffix}@example.com",
            password_hash=hash_password("billing-password"),
        )
        user.account = Account(balance=Decimal("0.30000000"))
        setup.add(user)
        await setup.commit()
        user_id = user.id
        account_id = user.account.id

    ready = asyncio.Event()
    entered = 0
    entered_lock = asyncio.Lock()

    async def charge_once(index: int) -> str:
        nonlocal entered
        async with AsyncSession(test_engine, expire_on_commit=False) as charge_session:
            async with entered_lock:
                entered += 1
                if entered == 2:
                    ready.set()
            await ready.wait()
            try:
                reservation = await reserve_balance(
                    charge_session,
                    user_id=user_id,
                    model=priced_model,
                    estimated_input_tokens=1,
                    max_output_tokens=1,
                    request_id=str(uuid4()),
                    idempotency_key=f"concurrent-reserve-{suffix}-{index}",
                )
            except InsufficientBalance:
                return "insufficient"
            await settle_request(
                charge_session,
                reservation_id=reservation.ledger_entry_id,
                model=priced_model,
                usage=CanonicalUsage(1, 1),
                idempotency_key=f"concurrent-settle-{suffix}-{index}",
            )
            return "charged"

    try:
        outcomes = await asyncio.gather(charge_once(1), charge_once(2))
        async with AsyncSession(test_engine, expire_on_commit=False) as check:
            account = await check.get(Account, account_id)
            assert account is not None
            assert sorted(outcomes) == ["charged", "insufficient"]
            assert account.balance == Decimal("0.10000000")
            assert account.total_spent == Decimal("0.20000000")
            assert account.balance >= 0
    finally:
        async with AsyncSession(test_engine) as cleanup:
            cleanup_user = await cleanup.get(User, user_id)
            if cleanup_user is not None:
                await cleanup.delete(cleanup_user)
                await cleanup.commit()


async def test_admin_adjustments_ledger_and_personal_balance_views(
    admin_client: AsyncClient,
    non_admin_client: AsyncClient,
    regular_user_record: User,
) -> None:
    regular_user_id = regular_user_record.id
    credit_key = f"credit-{uuid4().hex}"
    credit = await admin_client.post(
        f"/admin/users/{regular_user_id}/balance-adjustments",
        json={"amount": "1.25000000", "reason": "support credit", "idempotency_key": credit_key},
    )
    assert credit.status_code == 201
    assert Decimal(credit.json()["balance"]) == Decimal("1.25000000")

    duplicate = await admin_client.post(
        f"/admin/users/{regular_user_id}/balance-adjustments",
        json={"amount": "1.25000000", "reason": "support credit", "idempotency_key": credit_key},
    )
    assert duplicate.status_code == 201
    assert Decimal(duplicate.json()["balance"]) == Decimal("1.25000000")

    debit = await admin_client.post(
        f"/admin/users/{regular_user_id}/balance-adjustments",
        json={
            "amount": "-0.25000000",
            "reason": "manual debit",
            "idempotency_key": f"debit-{uuid4().hex}",
        },
    )
    assert debit.status_code == 201
    assert Decimal(debit.json()["balance"]) == Decimal("1.00000000")

    rejected = await admin_client.post(
        f"/admin/users/{regular_user_id}/balance-adjustments",
        json={
            "amount": "-1.00000001",
            "reason": "too large",
            "idempotency_key": f"debit-{uuid4().hex}",
        },
    )
    assert rejected.status_code == 402
    assert rejected.json()["detail"]["code"] == "insufficient_balance"

    ledger = await admin_client.get(f"/admin/users/{regular_user_id}/ledger")
    assert ledger.status_code == 200
    assert [item["kind"] for item in ledger.json()] == ["adjustment", "adjustment"]

    own_balance = await non_admin_client.get("/me/balance")
    assert own_balance.status_code == 200
    assert own_balance.json() == {"balance": "1.00000000", "total_spent": "0E-8"}
    assert "ledger" not in own_balance.json()

    forbidden = await non_admin_client.get(f"/admin/users/{regular_user_id}/ledger")
    assert forbidden.status_code == 403
