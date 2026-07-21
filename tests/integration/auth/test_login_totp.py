from collections.abc import AsyncIterator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.security import encrypt_secret, hash_password, issue_access_token
from ai_gateway.db.models import User
from ai_gateway.db.session import get_session
from ai_gateway.main import create_app


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="integration-test-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )


@pytest_asyncio.fixture
async def client(
    session: AsyncSession,
    auth_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


async def create_user(
    session: AsyncSession,
    *,
    email: str = "user@example.com",
    password: str = "correct horse battery staple",
    is_active: bool = True,
    totp_secret: str | None = None,
    settings: Settings | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        is_active=is_active,
        totp_enabled=totp_secret is not None,
        totp_secret_encrypted=(
            encrypt_secret(totp_secret, settings=settings)
            if totp_secret is not None and settings is not None
            else None
        ),
    )
    session.add(user)
    await session.flush()
    return user


def error_code(response_json: dict[str, object]) -> object:
    detail = response_json["detail"]
    assert isinstance(detail, dict)
    return detail["code"]


async def test_valid_password_without_totp_returns_token_pair(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await create_user(session)

    response = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]
    assert response.json()["token_type"] == "bearer"


async def test_totp_enabled_without_code_requires_totp(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    await create_user(
        session,
        totp_secret=pyotp.random_base32(),
        settings=auth_settings,
    )

    response = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 401
    assert error_code(response.json()) == "totp_required"


async def test_valid_password_and_totp_returns_token_pair(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    secret = pyotp.random_base32()
    await create_user(session, totp_secret=secret, settings=auth_settings)

    response = await client.post(
        "/auth/login",
        json={
            "email": "user@example.com",
            "password": "correct horse battery staple",
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


async def test_wrong_password_is_rejected(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await create_user(session)

    response = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert error_code(response.json()) == "invalid_credentials"


async def test_unknown_email_uses_generic_credentials_error(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert error_code(response.json()) == "invalid_credentials"


async def test_invalid_totp_is_rejected(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    secret = pyotp.random_base32()
    await create_user(
        session,
        totp_secret=secret,
        settings=auth_settings,
    )
    totp = pyotp.TOTP(secret)
    current_counter = totp.timecode(datetime.now(UTC))
    valid_codes = {totp.generate_otp(current_counter + offset) for offset in (-1, 0, 1)}
    invalid_code = next(
        f"{candidate:06d}"
        for candidate in range(1_000_000)
        if f"{candidate:06d}" not in valid_codes
    )

    response = await client.post(
        "/auth/login",
        json={
            "email": "user@example.com",
            "password": "correct horse battery staple",
            "totp_code": invalid_code,
        },
    )

    assert response.status_code == 401
    assert error_code(response.json()) == "invalid_totp"


async def test_disabled_user_is_rejected(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await create_user(session, is_active=False)

    response = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 403
    assert error_code(response.json()) == "user_disabled"


async def test_refresh_token_returns_new_access_token(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await create_user(session)
    login = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"


async def test_access_token_cannot_be_used_to_refresh(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await create_user(session)
    login = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": login.json()["access_token"]},
    )

    assert response.status_code == 401
    assert error_code(response.json()) == "invalid_token_type"


async def test_totp_setup_and_confirm_is_two_step(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    user = await create_user(session)
    access_token = issue_access_token(user_id=user.id, settings=auth_settings)
    headers = {"Authorization": f"Bearer {access_token}"}

    setup = await client.post("/auth/totp/setup", headers=headers)

    assert setup.status_code == 200
    uri = setup.json()["otpauth_uri"]
    assert uri.startswith("otpauth://totp/")
    assert user.totp_secret_encrypted is not None
    assert not user.totp_enabled
    secret = parse_qs(urlparse(uri).query)["secret"][0]
    assert secret.encode() not in user.totp_secret_encrypted

    confirm = await client.post(
        "/auth/totp/confirm",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now()},
    )

    assert confirm.status_code == 200
    assert confirm.json() == {"totp_enabled": True}
    assert "secret" not in confirm.text.lower()
    assert user.totp_enabled
