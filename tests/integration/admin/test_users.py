from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.enums import LedgerKind, Protocol
from ai_gateway.core.security import verify_password
from ai_gateway.db.models import Account, LedgerEntry, RequestLog, User


async def test_admin_can_create_user_and_account_atomically(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    response = await admin_client.post(
        "/admin/users",
        json={
            "email": "created@example.com",
            "password": "strong-created-password",
            "role": "user",
            "initial_balance": "12.34000000",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "created@example.com"
    assert body["role"] == "user"
    assert body["is_active"] is True
    assert Decimal(body["balance"]) == Decimal("12.34000000")
    assert Decimal(body["total_spent"]) == Decimal("0")
    assert body["created_at"].endswith("+00:00")
    assert body["updated_at"].endswith("+00:00")
    assert "password" not in body
    user = await session.scalar(select(User).where(User.id == body["id"]))
    assert user is not None
    assert verify_password("strong-created-password", user.password_hash)
    account = await session.scalar(select(Account).where(Account.user_id == user.id))
    assert account is not None
    assert account.balance == Decimal("12.34000000")


async def test_initial_balance_accepts_numeric_20_8_boundary(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/admin/users",
        json={
            "email": "balance-boundary@example.com",
            "password": "boundary-password",
            "initial_balance": "999999999999.99999999",
        },
    )

    assert response.status_code == 201
    assert response.json()["balance"] == "999999999999.99999999"


@pytest.mark.parametrize(
    "initial_balance",
    [
        "1000000000000.00000000",
        "999999999999.999999999",
        "-0.00000001",
    ],
)
async def test_initial_balance_rejects_values_outside_numeric_20_8(
    admin_client: AsyncClient,
    initial_balance: str,
) -> None:
    response = await admin_client.post(
        "/admin/users",
        json={
            "email": f"invalid-{initial_balance}@example.com",
            "password": "invalid-balance-password",
            "initial_balance": initial_balance,
        },
    )

    assert response.status_code == 422


async def test_admin_can_list_get_update_and_delete_users(
    admin_client: AsyncClient,
) -> None:
    created = await admin_client.post(
        "/admin/users",
        json={
            "email": "lifecycle@example.com",
            "password": "initial-password",
            "role": "user",
            "initial_balance": "0",
        },
    )
    user_id = created.json()["id"]

    listing = await admin_client.get("/admin/users")
    detail = await admin_client.get(f"/admin/users/{user_id}")
    updated = await admin_client.patch(
        f"/admin/users/{user_id}",
        json={
            "email": "updated@example.com",
            "password": "replacement-password",
            "role": "admin",
            "is_active": False,
        },
    )
    deleted = await admin_client.delete(f"/admin/users/{user_id}")
    missing = await admin_client.get(f"/admin/users/{user_id}")

    assert listing.status_code == 200
    listed_user = next(item for item in listing.json() if item["id"] == user_id)
    assert Decimal(listed_user["balance"]) == Decimal("0")
    assert Decimal(listed_user["total_spent"]) == Decimal("0")
    assert detail.status_code == 200
    assert Decimal(detail.json()["balance"]) == Decimal("0")
    assert Decimal(detail.json()["total_spent"]) == Decimal("0")
    assert updated.status_code == 200
    assert updated.json()["email"] == "updated@example.com"
    assert updated.json()["role"] == "admin"
    assert updated.json()["is_active"] is False
    assert "password" not in updated.json()
    assert deleted.status_code == 204
    assert missing.status_code == 404


async def test_list_users_returns_exact_accumulated_total_spend(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    billed_user = User(
        email="billed@example.com",
        password_hash="not-used-by-this-test",
        role="user",
    )
    billed_user.account = Account(
        balance=Decimal("8.75000000"),
        total_spent=Decimal("1.25000000"),
    )
    session.add(billed_user)
    await session.flush()
    session.add(
        LedgerEntry(
            account_id=billed_user.account.id,
            request_id="11111111-1111-1111-1111-111111111111",
            idempotency_key="users-total-spent-usage",
            kind=LedgerKind.USAGE,
            amount=Decimal("-1.25000000"),
            balance_after=Decimal("8.75000000"),
            metadata_json={"source": "test"},
        )
    )
    await session.flush()

    response = await admin_client.get("/admin/users")

    assert response.status_code == 200
    user_payload = next(item for item in response.json() if item["id"] == billed_user.id)
    assert user_payload["balance"] == "8.75000000"
    assert user_payload["total_spent"] == "1.25000000"


async def test_admin_cannot_disable_self(
    admin_client: AsyncClient,
    admin_user_record: User,
) -> None:
    response = await admin_client.patch(
        f"/admin/users/{admin_user_record.id}",
        json={"is_active": False},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_disable_forbidden"
    assert admin_user_record.is_active is True


async def test_admin_cannot_delete_self(
    admin_client: AsyncClient,
    admin_user_record: User,
) -> None:
    response = await admin_client.delete(f"/admin/users/{admin_user_record.id}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "self_delete_forbidden"


async def test_admin_must_disable_user_with_request_history_instead_of_deleting(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    created = await admin_client.post(
        "/admin/users",
        json={
            "email": "audited-user@example.com",
            "password": "audited-user-password",
        },
    )
    user_id = created.json()["id"]
    request_log = RequestLog(
        id=str(uuid4()),
        user_id=user_id,
        inbound_protocol=Protocol.OPENAI,
        transport="http",
    )
    session.add(request_log)
    await session.flush()

    response = await admin_client.delete(f"/admin/users/{user_id}")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "user_has_history",
        "message": "User has audit history; disable the user instead",
    }
    assert await session.get(User, user_id) is not None
    assert await session.get(RequestLog, request_log.id) is not None


async def test_admin_must_disable_user_with_ledger_history_instead_of_deleting(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    created = await admin_client.post(
        "/admin/users",
        json={
            "email": "ledger-user@example.com",
            "password": "ledger-user-password",
        },
    )
    user_id = created.json()["id"]
    account = await session.scalar(select(Account).where(Account.user_id == user_id))
    assert account is not None
    ledger_entry = LedgerEntry(
        account_id=account.id,
        idempotency_key="user-delete-ledger-history",
        kind=LedgerKind.ADJUSTMENT,
        amount=Decimal("1.00000000"),
        balance_after=Decimal("1.00000000"),
        metadata_json={"reason": "audit"},
    )
    session.add(ledger_entry)
    await session.flush()

    response = await admin_client.delete(f"/admin/users/{user_id}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "user_has_history"
    assert await session.get(User, user_id) is not None
    assert await session.get(LedgerEntry, ledger_entry.id) is not None


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/admin/users",
            {
                "email": "blocked@example.com",
                "password": "blocked-password",
                "role": "user",
                "initial_balance": "0",
            },
        ),
        ("PATCH", "/admin/users/1", {"is_active": False}),
        ("DELETE", "/admin/users/1", None),
    ],
)
async def test_non_admin_cannot_mutate_users(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    non_admin_client: AsyncClient,
) -> None:
    response = await non_admin_client.request(method, path, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"


async def test_non_admin_cannot_list_users(non_admin_client: AsyncClient) -> None:
    response = await non_admin_client.get("/admin/users")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"
