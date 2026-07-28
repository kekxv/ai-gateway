from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import parse_qs, urlparse

import jwt
import pyotp
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ai_gateway.auth.dependencies import admin_user, current_user
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.security import (
    decrypt_secret,
    encrypt_secret,
    hash_password,
    issue_access_token,
    issue_refresh_token,
)
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

    @app.get("/_test/protected")
    async def protected(user: Annotated[User, Depends(current_user)]) -> dict[str, int]:
        return {"user_id": user.id}

    @app.get("/_test/admin")
    async def admin_only(user: Annotated[User, Depends(admin_user)]) -> dict[str, int]:
        return {"user_id": user.id}

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
    role: str = "user",
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        is_active=is_active,
        role=role,
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


def expired_access_token(*, user_id: int, settings: Settings) -> str:
    issued_at = datetime.now(UTC) - timedelta(minutes=10)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iss": settings.jwt_issuer,
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=1),
            "jti": "expired-test-token",
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


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


async def test_initial_totp_setup_uses_pending_secret_until_confirmed(
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
    assert user.totp_secret_encrypted is None
    assert user.pending_totp_secret_encrypted is not None
    assert not user.totp_enabled
    secret = parse_qs(urlparse(uri).query)["secret"][0]
    assert secret.encode() not in user.pending_totp_secret_encrypted
    pending_ciphertext = user.pending_totp_secret_encrypted

    confirm = await client.post(
        "/auth/totp/confirm",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now()},
    )

    assert confirm.status_code == 200
    assert confirm.json() == {"totp_enabled": True}
    assert "secret" not in confirm.text.lower()
    assert user.totp_enabled
    assert user.pending_totp_secret_encrypted is None
    assert user.totp_secret_encrypted == pending_ciphertext
    assert decrypt_secret(user.totp_secret_encrypted, settings=auth_settings) == secret


async def test_totp_setup_accepts_normalized_custom_secret_until_confirmed(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    user = await create_user(session)
    access_token = issue_access_token(user_id=user.id, settings=auth_settings)
    headers = {"Authorization": f"Bearer {access_token}"}
    custom_secret = "jbsw y3dp-ehpk3pxp jbsw y3dp-ehpk3pxp"
    normalized_secret = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"

    setup = await client.post(
        "/auth/totp/setup",
        headers=headers,
        json={"custom_secret": custom_secret},
    )

    assert setup.status_code == 200
    uri_secret = parse_qs(urlparse(setup.json()["otpauth_uri"]).query)["secret"][0]
    assert uri_secret == normalized_secret
    assert user.totp_secret_encrypted is None
    assert user.pending_totp_secret_encrypted is not None
    assert normalized_secret.encode() not in user.pending_totp_secret_encrypted
    assert (
        decrypt_secret(user.pending_totp_secret_encrypted, settings=auth_settings)
        == normalized_secret
    )

    confirm = await client.post(
        "/auth/totp/confirm",
        headers=headers,
        json={"code": pyotp.TOTP(normalized_secret).now()},
    )

    assert confirm.status_code == 200
    assert user.totp_enabled
    assert user.pending_totp_secret_encrypted is None
    assert decrypt_secret(user.totp_secret_encrypted, settings=auth_settings) == normalized_secret


@pytest.mark.parametrize(
    "custom_secret",
    ["NOT-BASE32-0189", "JBSWY3DPEHPK3PXP", "A" * 129],
)
async def test_totp_setup_rejects_invalid_custom_secret_without_exposing_or_persisting_it(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
    custom_secret: str,
) -> None:
    user = await create_user(session)
    access_token = issue_access_token(user_id=user.id, settings=auth_settings)

    response = await client.post(
        "/auth/totp/setup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"custom_secret": custom_secret},
    )

    assert response.status_code == 422
    assert error_code(response.json()) == "invalid_totp_secret"
    assert custom_secret not in response.text
    assert user.pending_totp_secret_encrypted is None
    assert user.totp_secret_encrypted is None
    assert not user.totp_enabled


async def test_totp_reenrollment_with_custom_secret_still_requires_current_code(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    old_secret = pyotp.random_base32()
    custom_secret = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    user = await create_user(session, totp_secret=old_secret, settings=auth_settings)
    active_ciphertext = user.totp_secret_encrypted
    access_token = issue_access_token(user_id=user.id, settings=auth_settings)

    response = await client.post(
        "/auth/totp/setup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"custom_secret": custom_secret},
    )

    assert response.status_code == 401
    assert error_code(response.json()) == "current_totp_required"
    assert user.pending_totp_secret_encrypted is None
    assert user.totp_secret_encrypted == active_ciphertext


async def test_totp_reenrollment_requires_current_code(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    old_secret = pyotp.random_base32()
    user = await create_user(session, totp_secret=old_secret, settings=auth_settings)
    access_token = issue_access_token(user_id=user.id, settings=auth_settings)

    response = await client.post(
        "/auth/totp/setup",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 401
    assert error_code(response.json()) == "current_totp_required"
    assert user.pending_totp_secret_encrypted is None
    assert user.totp_enabled
    assert decrypt_secret(user.totp_secret_encrypted, settings=auth_settings) == old_secret


async def test_totp_reenrollment_rejects_invalid_current_code(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    old_secret = pyotp.random_base32()
    user = await create_user(session, totp_secret=old_secret, settings=auth_settings)
    access_token = issue_access_token(user_id=user.id, settings=auth_settings)

    response = await client.post(
        "/auth/totp/setup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"current_totp_code": "not-a-valid-code"},
    )

    assert response.status_code == 401
    assert error_code(response.json()) == "invalid_totp"
    assert user.pending_totp_secret_encrypted is None
    assert user.totp_enabled
    assert decrypt_secret(user.totp_secret_encrypted, settings=auth_settings) == old_secret


async def test_old_totp_stays_active_during_safe_reenrollment(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    old_secret = pyotp.random_base32()
    user = await create_user(session, totp_secret=old_secret, settings=auth_settings)
    old_ciphertext = user.totp_secret_encrypted
    access_token = issue_access_token(user_id=user.id, settings=auth_settings)
    headers = {"Authorization": f"Bearer {access_token}"}

    setup = await client.post(
        "/auth/totp/setup",
        headers=headers,
        json={"current_totp_code": pyotp.TOTP(old_secret).now()},
    )

    assert setup.status_code == 200
    new_secret = parse_qs(urlparse(setup.json()["otpauth_uri"]).query)["secret"][0]
    assert user.totp_enabled
    assert user.totp_secret_encrypted == old_ciphertext
    assert user.pending_totp_secret_encrypted is not None
    assert decrypt_secret(user.pending_totp_secret_encrypted, settings=auth_settings) == new_secret

    old_login = await client.post(
        "/auth/login",
        json={
            "email": user.email,
            "password": "correct horse battery staple",
            "totp_code": pyotp.TOTP(old_secret).now(),
        },
    )

    assert old_login.status_code == 200


async def test_totp_confirm_atomically_switches_to_pending_secret(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    old_secret = pyotp.random_base32()
    user = await create_user(session, totp_secret=old_secret, settings=auth_settings)
    access_token = issue_access_token(user_id=user.id, settings=auth_settings)
    headers = {"Authorization": f"Bearer {access_token}"}
    setup = await client.post(
        "/auth/totp/setup",
        headers=headers,
        json={"current_totp_code": pyotp.TOTP(old_secret).now()},
    )
    new_secret = parse_qs(urlparse(setup.json()["otpauth_uri"]).query)["secret"][0]
    pending_ciphertext = user.pending_totp_secret_encrypted

    confirm = await client.post(
        "/auth/totp/confirm",
        headers=headers,
        json={"code": pyotp.TOTP(new_secret).now()},
    )

    assert confirm.status_code == 200
    assert user.totp_enabled
    assert user.totp_secret_encrypted == pending_ciphertext
    assert user.pending_totp_secret_encrypted is None
    assert decrypt_secret(user.totp_secret_encrypted, settings=auth_settings) == new_secret

    old_login = await client.post(
        "/auth/login",
        json={
            "email": user.email,
            "password": "correct horse battery staple",
            "totp_code": pyotp.TOTP(old_secret).now(),
        },
    )
    new_login = await client.post(
        "/auth/login",
        json={
            "email": user.email,
            "password": "correct horse battery staple",
            "totp_code": pyotp.TOTP(new_secret).now(),
        },
    )

    assert old_login.status_code == 401
    assert error_code(old_login.json()) == "invalid_totp"
    assert new_login.status_code == 200


async def test_totp_setup_refreshes_stale_preloaded_active_state_under_lock(
    test_engine: AsyncEngine,
    auth_settings: Settings,
) -> None:
    async with AsyncSession(test_engine, expire_on_commit=False) as seed_session:
        user = await create_user(seed_session)
        await seed_session.commit()
        user_id = user.id

    old_secret = pyotp.random_base32()
    old_ciphertext = encrypt_secret(old_secret, settings=auth_settings)
    try:
        async with AsyncSession(test_engine, expire_on_commit=False) as request_session:
            stale_user = await request_session.get(User, user_id)
            assert stale_user is not None
            assert not stale_user.totp_enabled

            async with AsyncSession(test_engine, expire_on_commit=False) as concurrent_session:
                concurrent_user = await concurrent_session.get(User, user_id)
                assert concurrent_user is not None
                concurrent_user.totp_enabled = True
                concurrent_user.totp_secret_encrypted = old_ciphertext
                await concurrent_session.commit()

            app = create_app()

            async def override_session() -> AsyncIterator[AsyncSession]:
                yield request_session

            app.dependency_overrides[get_session] = override_session
            app.dependency_overrides[get_settings] = lambda: auth_settings
            access_token = issue_access_token(user_id=user_id, settings=auth_settings)
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as concurrent_client:
                response = await concurrent_client.post(
                    "/auth/totp/setup",
                    headers={"Authorization": f"Bearer {access_token}"},
                )

            assert response.status_code == 401
            assert error_code(response.json()) == "current_totp_required"
    finally:
        async with AsyncSession(test_engine) as cleanup_session:
            cleanup_user = await cleanup_session.get(User, user_id)
            if cleanup_user is not None:
                await cleanup_session.delete(cleanup_user)
                await cleanup_session.commit()


async def test_totp_confirm_cannot_reactivate_stale_pending_secret_after_concurrent_confirm(
    test_engine: AsyncEngine,
    auth_settings: Settings,
) -> None:
    stale_pending_secret = pyotp.random_base32()
    stale_pending_ciphertext = encrypt_secret(stale_pending_secret, settings=auth_settings)
    async with AsyncSession(test_engine, expire_on_commit=False) as seed_session:
        user = await create_user(seed_session)
        user.pending_totp_secret_encrypted = stale_pending_ciphertext
        await seed_session.commit()
        user_id = user.id

    active_secret = pyotp.random_base32()
    active_ciphertext = encrypt_secret(active_secret, settings=auth_settings)
    try:
        async with AsyncSession(test_engine, expire_on_commit=False) as request_session:
            stale_user = await request_session.get(User, user_id)
            assert stale_user is not None
            assert stale_user.pending_totp_secret_encrypted == stale_pending_ciphertext
            assert not stale_user.totp_enabled

            async with AsyncSession(test_engine, expire_on_commit=False) as concurrent_session:
                concurrent_user = await concurrent_session.get(User, user_id)
                assert concurrent_user is not None
                concurrent_user.totp_secret_encrypted = active_ciphertext
                concurrent_user.pending_totp_secret_encrypted = None
                concurrent_user.totp_enabled = True
                await concurrent_session.commit()

            app = create_app()

            async def override_session() -> AsyncIterator[AsyncSession]:
                yield request_session

            app.dependency_overrides[get_session] = override_session
            app.dependency_overrides[get_settings] = lambda: auth_settings
            access_token = issue_access_token(user_id=user_id, settings=auth_settings)
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as concurrent_client:
                response = await concurrent_client.post(
                    "/auth/totp/confirm",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"code": pyotp.TOTP(stale_pending_secret).now()},
                )

            assert response.status_code == 400
            assert error_code(response.json()) == "totp_not_configured"

        async with AsyncSession(test_engine) as verification_session:
            persisted_user = await verification_session.get(User, user_id)
            assert persisted_user is not None
            assert persisted_user.totp_enabled
            assert persisted_user.pending_totp_secret_encrypted is None
            assert persisted_user.totp_secret_encrypted == active_ciphertext
    finally:
        async with AsyncSession(test_engine) as cleanup_session:
            cleanup_user = await cleanup_session.get(User, user_id)
            if cleanup_user is not None:
                await cleanup_session.delete(cleanup_user)
                await cleanup_session.commit()


@pytest.mark.parametrize(
    ("headers", "expected_code"),
    [
        ({}, "authentication_required"),
        ({"Authorization": "Bearer malformed"}, "invalid_token"),
    ],
)
async def test_current_user_rejects_missing_or_malformed_token(
    client: AsyncClient,
    headers: dict[str, str],
    expected_code: str,
) -> None:
    response = await client.get("/_test/protected", headers=headers)

    assert response.status_code == 401
    assert error_code(response.json()) == expected_code


async def test_current_user_rejects_refresh_and_expired_tokens(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    user = await create_user(session)
    refresh = issue_refresh_token(user_id=user.id, settings=auth_settings)
    expired = expired_access_token(user_id=user.id, settings=auth_settings)

    refresh_response = await client.get(
        "/_test/protected",
        headers={"Authorization": f"Bearer {refresh}"},
    )
    expired_response = await client.get(
        "/_test/protected",
        headers={"Authorization": f"Bearer {expired}"},
    )

    assert refresh_response.status_code == 401
    assert error_code(refresh_response.json()) == "invalid_token"
    assert expired_response.status_code == 401
    assert error_code(expired_response.json()) == "invalid_token"


@pytest.mark.parametrize("delete_user", [False, True])
async def test_disabled_or_deleted_user_cannot_use_protected_or_refresh(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
    delete_user: bool,
) -> None:
    user = await create_user(session)
    access = issue_access_token(user_id=user.id, settings=auth_settings)
    refresh = issue_refresh_token(user_id=user.id, settings=auth_settings)
    if delete_user:
        await session.delete(user)
    else:
        user.is_active = False
    await session.flush()

    protected_response = await client.get(
        "/_test/protected",
        headers={"Authorization": f"Bearer {access}"},
    )
    refresh_response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh},
    )

    expected_status = 401 if delete_user else 403
    expected_code = "invalid_token" if delete_user else "user_disabled"
    assert protected_response.status_code == expected_status
    assert error_code(protected_response.json()) == expected_code
    assert refresh_response.status_code == expected_status
    assert error_code(refresh_response.json()) == expected_code


async def test_admin_user_accepts_admin_and_rejects_non_admin(
    client: AsyncClient,
    session: AsyncSession,
    auth_settings: Settings,
) -> None:
    admin = await create_user(session, email="admin@example.com", role="admin")
    regular = await create_user(session, email="regular@example.com")
    admin_token = issue_access_token(user_id=admin.id, settings=auth_settings)
    regular_token = issue_access_token(user_id=regular.id, settings=auth_settings)

    accepted = await client.get(
        "/_test/admin",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    rejected = await client.get(
        "/_test/admin",
        headers={"Authorization": f"Bearer {regular_token}"},
    )

    assert accepted.status_code == 200
    assert accepted.json() == {"user_id": admin.id}
    assert rejected.status_code == 403
    assert error_code(rejected.json()) == "admin_required"
