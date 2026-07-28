from collections.abc import AsyncIterator
from datetime import UTC, datetime

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
def account_security_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="account-security-test-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )


@pytest_asyncio.fixture
async def account_security_client(
    session: AsyncSession,
    account_security_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: account_security_settings
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


async def create_security_user(
    session: AsyncSession,
    *,
    settings: Settings,
    totp_secret: str | None = None,
) -> tuple[User, dict[str, str]]:
    user = User(
        email="security-user@example.com",
        password_hash=hash_password("current-account-password"),
        totp_enabled=totp_secret is not None,
        totp_secret_encrypted=(
            encrypt_secret(totp_secret, settings=settings) if totp_secret is not None else None
        ),
        pending_totp_secret_encrypted=(
            encrypt_secret(pyotp.random_base32(), settings=settings)
            if totp_secret is not None
            else None
        ),
    )
    session.add(user)
    await session.flush()
    token = issue_access_token(user_id=user.id, settings=settings)
    return user, {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/auth/password",
            {
                "current_password": "current-account-password",
                "new_password": "replacement-account-password",
            },
        ),
        (
            "/auth/totp/disable",
            {"current_password": "current-account-password", "code": "123456"},
        ),
    ],
)
async def test_account_security_mutations_require_authentication(
    account_security_client: AsyncClient,
    path: str,
    payload: dict[str, str],
) -> None:
    response = await account_security_client.post(path, json=payload)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


async def test_password_change_rejects_wrong_current_password(
    account_security_client: AsyncClient,
    session: AsyncSession,
    account_security_settings: Settings,
) -> None:
    _, headers = await create_security_user(
        session,
        settings=account_security_settings,
    )

    response = await account_security_client.post(
        "/auth/password",
        headers=headers,
        json={
            "current_password": "wrong-current-password",
            "new_password": "replacement-account-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


async def test_password_change_rejects_short_new_password_without_echoing_it(
    account_security_client: AsyncClient,
    session: AsyncSession,
    account_security_settings: Settings,
) -> None:
    _, headers = await create_security_user(
        session,
        settings=account_security_settings,
    )

    response = await account_security_client.post(
        "/auth/password",
        headers=headers,
        json={"current_password": "current-account-password", "new_password": "P@5!"},
    )

    assert response.status_code == 422
    assert "P@5!" not in response.text


async def test_password_change_replaces_login_password_without_echoing_secrets(
    account_security_client: AsyncClient,
    session: AsyncSession,
    account_security_settings: Settings,
) -> None:
    _, headers = await create_security_user(
        session,
        settings=account_security_settings,
    )
    payload = {
        "current_password": "current-account-password",
        "new_password": "replacement-account-password",
    }

    changed = await account_security_client.post(
        "/auth/password",
        headers=headers,
        json=payload,
    )
    old_login = await account_security_client.post(
        "/auth/login",
        json={
            "email": "security-user@example.com",
            "password": payload["current_password"],
        },
    )
    new_login = await account_security_client.post(
        "/auth/login",
        json={
            "email": "security-user@example.com",
            "password": payload["new_password"],
        },
    )

    assert changed.status_code == 204
    assert changed.text == ""
    assert old_login.status_code == 401
    assert new_login.status_code == 200


async def test_totp_disable_rejects_wrong_password_and_wrong_code(
    account_security_client: AsyncClient,
    session: AsyncSession,
    account_security_settings: Settings,
) -> None:
    secret = pyotp.random_base32()
    _, headers = await create_security_user(
        session,
        settings=account_security_settings,
        totp_secret=secret,
    )
    totp = pyotp.TOTP(secret)
    current_counter = totp.timecode(datetime.now(UTC))
    valid_codes = {totp.generate_otp(current_counter + offset) for offset in (-1, 0, 1)}
    invalid_code = next(
        f"{candidate:06d}"
        for candidate in range(1_000_000)
        if f"{candidate:06d}" not in valid_codes
    )

    wrong_password = await account_security_client.post(
        "/auth/totp/disable",
        headers=headers,
        json={"current_password": "wrong-password", "code": totp.now()},
    )
    wrong_code = await account_security_client.post(
        "/auth/totp/disable",
        headers=headers,
        json={
            "current_password": "current-account-password",
            "code": invalid_code,
        },
    )

    assert wrong_password.status_code == 401
    assert wrong_password.json()["detail"]["code"] == "invalid_credentials"
    assert wrong_code.status_code == 401
    assert wrong_code.json()["detail"]["code"] == "invalid_totp"


async def test_totp_disable_clears_active_and_pending_secrets(
    account_security_client: AsyncClient,
    session: AsyncSession,
    account_security_settings: Settings,
) -> None:
    secret = pyotp.random_base32()
    user, headers = await create_security_user(
        session,
        settings=account_security_settings,
        totp_secret=secret,
    )

    disabled = await account_security_client.post(
        "/auth/totp/disable",
        headers=headers,
        json={
            "current_password": "current-account-password",
            "code": pyotp.TOTP(secret).now(),
        },
    )
    login = await account_security_client.post(
        "/auth/login",
        json={
            "email": "security-user@example.com",
            "password": "current-account-password",
        },
    )

    assert disabled.status_code == 200
    assert disabled.json() == {"totp_enabled": False}
    assert user.totp_enabled is False
    assert user.totp_secret_encrypted is None
    assert user.pending_totp_secret_encrypted is None
    assert login.status_code == 200


async def test_totp_disable_rejects_accounts_without_totp(
    account_security_client: AsyncClient,
    session: AsyncSession,
    account_security_settings: Settings,
) -> None:
    _, headers = await create_security_user(
        session,
        settings=account_security_settings,
    )

    response = await account_security_client.post(
        "/auth/totp/disable",
        headers=headers,
        json={"current_password": "current-account-password", "code": "123456"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "totp_not_enabled"
