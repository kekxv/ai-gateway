from collections.abc import AsyncIterator
from datetime import UTC

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.security import hash_password, issue_access_token
from ai_gateway.db.models import User
from ai_gateway.db.session import get_session
from ai_gateway.main import create_app


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="current-user-test-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )


@pytest_asyncio.fixture
async def auth_client(
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
    ) as client:
        yield client


@pytest_asyncio.fixture
async def admin_user(session: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        password_hash=hash_password("admin-password"),
        role="admin",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@pytest.fixture
def access_token(admin_user: User, auth_settings: Settings) -> str:
    return issue_access_token(user_id=admin_user.id, settings=auth_settings)


async def test_get_me_returns_authenticated_user(
    auth_client: AsyncClient,
    admin_user: User,
    access_token: str,
) -> None:
    response = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": admin_user.id,
        "email": admin_user.email,
        "role": "admin",
        "is_active": True,
        "totp_enabled": False,
        "created_at": admin_user.created_at.replace(tzinfo=UTC).isoformat(),
        "updated_at": admin_user.updated_at.replace(tzinfo=UTC).isoformat(),
    }


async def test_get_me_rejects_missing_bearer_token(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
