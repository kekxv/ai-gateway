from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.db.models import User
from ai_gateway.db.session import get_session
from ai_gateway.main import create_app


@pytest.fixture
def registration_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="registration-test-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )


@pytest_asyncio.fixture
async def registration_client(
    session: AsyncSession,
    registration_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: registration_settings
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


async def test_first_registered_user_is_admin_and_later_user_is_regular(
    registration_client: AsyncClient,
    session: AsyncSession,
) -> None:
    first = await registration_client.post(
        "/auth/register",
        json={"email": " First.Admin@Example.com ", "password": "first-password"},
    )
    second = await registration_client.post(
        "/auth/register",
        json={"email": "member@example.com", "password": "member-password"},
    )

    assert first.status_code == 201
    assert first.json()["access_token"]
    assert first.json()["refresh_token"]
    assert first.json()["token_type"] == "bearer"
    assert second.status_code == 201

    users = list(
        await session.scalars(select(User).options(joinedload(User.account)).order_by(User.id))
    )
    assert [(user.email, user.role) for user in users] == [
        ("first.admin@example.com", "admin"),
        ("member@example.com", "user"),
    ]
    assert users[0].account is not None
    assert users[0].account.balance == Decimal("0.00000000")
    assert users[1].account is not None
    assert users[1].account.balance == Decimal("0.00000000")


async def test_registered_credentials_can_log_in(
    registration_client: AsyncClient,
) -> None:
    registered = await registration_client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "registered-password"},
    )

    login = await registration_client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "registered-password"},
    )

    assert registered.status_code == 201
    assert login.status_code == 200
    assert login.json()["access_token"]


async def test_registration_status_is_public_and_enabled_by_default(
    registration_client: AsyncClient,
) -> None:
    response = await registration_client.get("/auth/registration")

    assert response.status_code == 200
    assert response.json() == {"enabled": True}


async def test_administrator_can_disable_and_reenable_registration(
    registration_client: AsyncClient,
) -> None:
    administrator = await registration_client.post(
        "/auth/register",
        json={"email": "admin@example.com", "password": "administrator-password"},
    )
    headers = {"Authorization": f"Bearer {administrator.json()['access_token']}"}

    disabled = await registration_client.patch(
        "/admin/settings/registration",
        headers=headers,
        json={"enabled": False},
    )
    public_status = await registration_client.get("/auth/registration")
    rejected = await registration_client.post(
        "/auth/register",
        json={"email": "blocked@example.com", "password": "registration-password"},
    )

    assert disabled.status_code == 200
    assert disabled.json() == {"enabled": False}
    assert public_status.json() == {"enabled": False}
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "registration_disabled"
    assert "registration-password" not in rejected.text

    enabled = await registration_client.patch(
        "/admin/settings/registration",
        headers=headers,
        json={"enabled": True},
    )
    accepted = await registration_client.post(
        "/auth/register",
        json={"email": "accepted@example.com", "password": "registration-password"},
    )

    assert enabled.status_code == 200
    assert enabled.json() == {"enabled": True}
    assert accepted.status_code == 201


async def test_duplicate_registration_uses_safe_conflict(
    registration_client: AsyncClient,
) -> None:
    payload = {"email": "duplicate@example.com", "password": "duplicate-password"}
    first = await registration_client.post("/auth/register", json=payload)
    duplicate = await registration_client.post("/auth/register", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "email_exists"
    assert "duplicate-password" not in duplicate.text


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "ab", "password": "long-enough-password"},
        {"email": "short-password@example.com", "password": "P@5!"},
        {
            "email": "extra@example.com",
            "password": "long-enough-password",
            "role": "admin",
        },
    ],
)
async def test_registration_rejects_invalid_or_privileged_payloads_without_echoing_password(
    registration_client: AsyncClient,
    payload: dict[str, str],
) -> None:
    response = await registration_client.post("/auth/register", json=payload)

    assert response.status_code == 422
    assert payload["password"] not in response.text
