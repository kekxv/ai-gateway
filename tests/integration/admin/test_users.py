from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.security import verify_password
from ai_gateway.db.models import Account, User


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
    assert "password" not in body
    user = await session.scalar(select(User).where(User.id == body["id"]))
    assert user is not None
    assert verify_password("strong-created-password", user.password_hash)
    account = await session.scalar(select(Account).where(Account.user_id == user.id))
    assert account is not None
    assert account.balance == Decimal("12.34000000")


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
    assert user_id in {item["id"] for item in listing.json()}
    assert detail.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["email"] == "updated@example.com"
    assert updated.json()["role"] == "admin"
    assert updated.json()["is_active"] is False
    assert "password" not in updated.json()
    assert deleted.status_code == 204
    assert missing.status_code == 404


async def test_non_admin_cannot_manage_users(non_admin_client: AsyncClient) -> None:
    response = await non_admin_client.get("/admin/users")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"
