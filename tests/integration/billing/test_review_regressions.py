from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_gateway.billing.service import (
    BillingService,
    IdempotencyConflict,
    InsufficientBalance,
    adjust_balance,
    reserve_balance,
    settle_request,
)
from ai_gateway.core.config import Settings
from ai_gateway.core.security import hash_password, issue_access_token
from ai_gateway.db.models import Account, LedgerEntry, Model, Provider, User
from ai_gateway.main import create_app
from ai_gateway.protocols.types import CanonicalUsage


@dataclass(frozen=True, slots=True)
class BillingIdentity:
    user_id: int
    account_id: int


@pytest_asyncio.fixture
async def committed_identity(test_engine: AsyncEngine) -> BillingIdentity:
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        user = User(
            email=f"billing-review-{uuid4().hex}@example.com",
            password_hash=hash_password("billing-password"),
        )
        user.account = Account(balance=Decimal("1.00000000"))
        setup.add(user)
        await setup.commit()
        identity = BillingIdentity(user.id, user.account.id)
    yield identity
    async with AsyncSession(test_engine) as cleanup:
        user = await cleanup.get(User, identity.user_id)
        if user is not None:
            await cleanup.delete(user)
            await cleanup.commit()


@pytest.fixture
def priced_model() -> Model:
    return Model(
        canonical_name="billing-review-model",
        display_name="Billing review model",
        input_price_per_million=Decimal("100000.00000000"),
        output_price_per_million=Decimal("100000.00000000"),
    )


@pytest.fixture
def billing_service(test_engine: AsyncEngine) -> BillingService:
    return BillingService(
        async_sessionmaker(test_engine, expire_on_commit=False),
        default_max_output_tokens=2,
    )


@pytest.mark.parametrize("outcome", ["success", "failure", "replay"])
async def test_public_mutations_never_flush_commit_or_rollback_caller_session(
    test_engine: AsyncEngine,
    committed_identity: BillingIdentity,
    priced_model: Model,
    outcome: str,
) -> None:
    provider_name = f"unrelated-billing-{outcome}-{uuid4().hex}"
    caller = AsyncSession(test_engine, expire_on_commit=False)
    unrelated = Provider(name=provider_name, credential_encrypted=b"unrelated")
    caller.add(unrelated)
    request_id = str(uuid4())
    key = f"isolation-{outcome}-{uuid4().hex}"

    try:
        if outcome == "failure":
            with pytest.raises(InsufficientBalance):
                await reserve_balance(
                    caller,
                    user_id=committed_identity.user_id,
                    model=priced_model,
                    estimated_input_tokens=1,
                    max_output_tokens=20,
                    request_id=request_id,
                    idempotency_key=key,
                )
            expected_balance = Decimal("1.00000000")
        else:
            first = await reserve_balance(
                caller,
                user_id=committed_identity.user_id,
                model=priced_model,
                estimated_input_tokens=1,
                max_output_tokens=1,
                request_id=request_id,
                idempotency_key=key,
            )
            if outcome == "replay":
                second = await reserve_balance(
                    caller,
                    user_id=committed_identity.user_id,
                    model=priced_model,
                    estimated_input_tokens=1,
                    max_output_tokens=1,
                    request_id=request_id,
                    idempotency_key=key,
                )
                assert second == first
            expected_balance = Decimal("0.80000000")

        assert unrelated.id is None
        async with AsyncSession(test_engine, expire_on_commit=False) as observer:
            assert (
                await observer.scalar(
                    select(func.count()).select_from(Provider).where(Provider.name == provider_name)
                )
                == 0
            )
            account = await observer.get(Account, committed_identity.account_id)
            assert account is not None
            assert account.balance == expected_balance

        await caller.rollback()
        async with AsyncSession(test_engine, expire_on_commit=False) as observer:
            assert (
                await observer.scalar(
                    select(func.count()).select_from(Provider).where(Provider.name == provider_name)
                )
                == 0
            )
            account = await observer.get(Account, committed_identity.account_id)
            assert account is not None
            assert account.balance == expected_balance
    finally:
        await caller.close()


async def test_settlement_ignores_caller_repeatable_read_snapshot(
    test_engine: AsyncEngine,
    committed_identity: BillingIdentity,
    priced_model: Model,
) -> None:
    caller = AsyncSession(test_engine, expire_on_commit=False)
    try:
        stale = await caller.get(Account, committed_identity.account_id)
        assert stale is not None
        assert stale.balance == Decimal("1.00000000")

        async with AsyncSession(test_engine, expire_on_commit=False) as reservation_session:
            reservation = await reserve_balance(
                reservation_session,
                user_id=committed_identity.user_id,
                model=priced_model,
                estimated_input_tokens=1,
                max_output_tokens=1,
                request_id=str(uuid4()),
                idempotency_key=f"late-reservation-{uuid4().hex}",
            )

        result = await settle_request(
            caller,
            reservation_id=reservation.ledger_entry_id,
            model=priced_model,
            usage=CanonicalUsage(1, 1),
            idempotency_key=f"late-settlement-{uuid4().hex}",
        )

        assert result.balance == Decimal("0.80000000")
        assert stale.balance == Decimal("1.00000000")
    finally:
        await caller.rollback()
        await caller.close()


async def test_adjustment_and_settlement_wrappers_leave_caller_work_untouched(
    test_engine: AsyncEngine,
    billing_service: BillingService,
    committed_identity: BillingIdentity,
    priced_model: Model,
) -> None:
    caller = AsyncSession(test_engine, expire_on_commit=False)
    provider_name = f"unrelated-adjust-settle-{uuid4().hex}"
    unrelated = Provider(name=provider_name, credential_encrypted=b"unrelated")
    caller.add(unrelated)
    adjustment_key = f"isolated-adjustment-{uuid4().hex}"
    try:
        adjustment = await adjust_balance(
            caller,
            user_id=committed_identity.user_id,
            amount=Decimal("1.00000000"),
            reason="isolated credit",
            idempotency_key=adjustment_key,
        )
        replay = await adjust_balance(
            caller,
            user_id=committed_identity.user_id,
            amount=Decimal("1.00000000"),
            reason="isolated credit",
            idempotency_key=adjustment_key,
        )
        assert replay == adjustment
        with pytest.raises(InsufficientBalance):
            await adjust_balance(
                caller,
                user_id=committed_identity.user_id,
                amount=Decimal("-3.00000000"),
                reason="rejected debit",
                idempotency_key=f"rejected-adjustment-{uuid4().hex}",
            )

        reservation = await billing_service.reserve_balance(
            user_id=committed_identity.user_id,
            model=priced_model,
            estimated_input_tokens=1,
            max_output_tokens=1,
            request_id=str(uuid4()),
            idempotency_key=f"isolated-reservation-{uuid4().hex}",
        )
        settled = await settle_request(
            caller,
            reservation_id=reservation.ledger_entry_id,
            model=priced_model,
            usage=CanonicalUsage(1, 1),
            idempotency_key=f"isolated-settlement-{uuid4().hex}",
        )

        assert settled.balance == Decimal("1.80000000")
        assert unrelated.id is None
        async with AsyncSession(test_engine, expire_on_commit=False) as observer:
            assert (
                await observer.scalar(
                    select(func.count()).select_from(Provider).where(Provider.name == provider_name)
                )
                == 0
            )
            account = await observer.get(Account, committed_identity.account_id)
            assert account is not None
            assert account.balance == Decimal("1.80000000")
            assert account.total_spent == Decimal("0.20000000")
        await caller.rollback()
        assert unrelated.id is None
    finally:
        await caller.close()


async def test_reservation_replay_rejects_changed_payload_and_completed_reservation(
    billing_service: BillingService,
    committed_identity: BillingIdentity,
    priced_model: Model,
) -> None:
    request_id = str(uuid4())
    key = f"fingerprint-{uuid4().hex}"
    reservation = await billing_service.reserve_balance(
        user_id=committed_identity.user_id,
        model=priced_model,
        estimated_input_tokens=1,
        max_output_tokens=1,
        request_id=request_id,
        idempotency_key=key,
    )

    with pytest.raises(IdempotencyConflict):
        await billing_service.reserve_balance(
            user_id=committed_identity.user_id,
            model=priced_model,
            estimated_input_tokens=2,
            max_output_tokens=1,
            request_id=request_id,
            idempotency_key=key,
        )

    await billing_service.settle_request(
        reservation_id=reservation.ledger_entry_id,
        model=priced_model,
        usage=CanonicalUsage(1, 1),
        idempotency_key=f"fingerprint-settle-{uuid4().hex}",
    )
    with pytest.raises(IdempotencyConflict):
        await billing_service.reserve_balance(
            user_id=committed_identity.user_id,
            model=priced_model,
            estimated_input_tokens=1,
            max_output_tokens=1,
            request_id=request_id,
            idempotency_key=key,
        )


async def test_settlement_replay_rejects_changed_key_or_payload(
    billing_service: BillingService,
    committed_identity: BillingIdentity,
    priced_model: Model,
) -> None:
    reservation = await billing_service.reserve_balance(
        user_id=committed_identity.user_id,
        model=priced_model,
        estimated_input_tokens=1,
        max_output_tokens=1,
        request_id=str(uuid4()),
        idempotency_key=f"settlement-replay-reserve-{uuid4().hex}",
    )
    settlement_key = f"settlement-replay-{uuid4().hex}"
    await billing_service.settle_request(
        reservation_id=reservation.ledger_entry_id,
        model=priced_model,
        usage=CanonicalUsage(1, 1),
        idempotency_key=settlement_key,
    )

    with pytest.raises(IdempotencyConflict):
        await billing_service.settle_request(
            reservation_id=reservation.ledger_entry_id,
            model=priced_model,
            usage=CanonicalUsage(1, 1),
            idempotency_key=f"different-{uuid4().hex}",
        )
    with pytest.raises(IdempotencyConflict):
        await billing_service.settle_request(
            reservation_id=reservation.ledger_entry_id,
            model=priced_model,
            usage=CanonicalUsage(2, 1),
            idempotency_key=settlement_key,
        )


async def test_adjustment_replay_returns_current_coherent_account_snapshot(
    test_engine: AsyncEngine,
    billing_service: BillingService,
    committed_identity: BillingIdentity,
    priced_model: Model,
) -> None:
    adjustment_key = f"coherent-adjustment-{uuid4().hex}"
    first = await billing_service.adjust_balance(
        user_id=committed_identity.user_id,
        amount=Decimal("1.00000000"),
        reason="credit",
        idempotency_key=adjustment_key,
    )
    assert first.balance == Decimal("2.00000000")
    reservation = await billing_service.reserve_balance(
        user_id=committed_identity.user_id,
        model=priced_model,
        estimated_input_tokens=1,
        max_output_tokens=1,
        request_id=str(uuid4()),
        idempotency_key=f"coherent-reserve-{uuid4().hex}",
    )
    await billing_service.settle_request(
        reservation_id=reservation.ledger_entry_id,
        model=priced_model,
        usage=CanonicalUsage(1, 1),
        idempotency_key=f"coherent-settle-{uuid4().hex}",
    )

    async with AsyncSession(test_engine, expire_on_commit=False) as caller:
        replay = await adjust_balance(
            caller,
            user_id=committed_identity.user_id,
            amount=Decimal("1.00000000"),
            reason="credit",
            idempotency_key=adjustment_key,
        )

    assert replay.balance == Decimal("1.80000000")
    assert replay.total_spent == Decimal("0.20000000")


async def test_app_scoped_billing_service_and_whitespace_validation(
    test_engine: AsyncEngine,
) -> None:
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        admin = User(
            email=f"billing-app-admin-{uuid4().hex}@example.com",
            password_hash=hash_password("admin-password"),
            role="admin",
        )
        admin.account = Account()
        member = User(
            email=f"billing-app-member-{uuid4().hex}@example.com",
            password_hash=hash_password("member-password"),
        )
        member.account = Account()
        setup.add_all((admin, member))
        await setup.commit()
        admin_id = admin.id
        member_id = member.id

    settings = Settings(
        environment="test",
        database_url=test_engine.url.render_as_string(hide_password=False),
        jwt_secret="billing-review-app-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
        billing_default_max_output_tokens=321,
    )
    app = create_app(settings)
    assert isinstance(app.state.billing_service, BillingService)
    assert app.state.billing_service.default_max_output_tokens == 321
    token = issue_access_token(user_id=admin_id, settings=settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            for payload in (
                {"amount": "1", "reason": "   ", "idempotency_key": "valid-key"},
                {"amount": "1", "reason": "valid", "idempotency_key": "   "},
            ):
                response = await client.post(
                    f"/admin/users/{member_id}/balance-adjustments",
                    json=payload,
                )
                assert response.status_code == 422
                assert "   " not in response.text

            accepted = await client.post(
                f"/admin/users/{member_id}/balance-adjustments",
                json={
                    "amount": "1.00000000",
                    "reason": "  trimmed reason  ",
                    "idempotency_key": "  trimmed-key  ",
                },
            )
            assert accepted.status_code == 201
        async with AsyncSession(test_engine, expire_on_commit=False) as check:
            entry = await check.scalar(
                select(LedgerEntry).where(LedgerEntry.account_id == member.account.id)
            )
            assert entry is not None
            assert entry.idempotency_key == "trimmed-key"
            assert entry.metadata_json["reason"] == "trimmed reason"
    finally:
        await app.state.engine.dispose()
        async with AsyncSession(test_engine) as cleanup:
            for user_id in (admin_id, member_id):
                user = await cleanup.get(User, user_id)
                if user is not None:
                    await cleanup.delete(user)
            await cleanup.commit()
