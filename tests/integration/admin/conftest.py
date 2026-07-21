from collections.abc import AsyncIterator

import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.security import hash_password, issue_access_token
from ai_gateway.db.models import Account, User
from ai_gateway.db.session import get_session
from ai_gateway.main import create_app


@pytest_asyncio.fixture
async def admin_user_record(session: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        password_hash=hash_password("admin-password"),
        role="admin",
    )
    user.account = Account()
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def regular_user_record(session: AsyncSession) -> User:
    user = User(
        email="member@example.com",
        password_hash=hash_password("member-password"),
        role="user",
    )
    user.account = Account()
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def admin_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="admin-integration-test-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )


async def _client_for_user(
    *,
    session: AsyncSession,
    settings: Settings,
    user: User,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    token = issue_access_token(user_id=user.id, settings=settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def admin_client(
    session: AsyncSession,
    admin_settings: Settings,
    admin_user_record: User,
) -> AsyncIterator[AsyncClient]:
    async for client in _client_for_user(
        session=session,
        settings=admin_settings,
        user=admin_user_record,
    ):
        yield client


@pytest_asyncio.fixture
async def non_admin_client(
    session: AsyncSession,
    admin_settings: Settings,
    regular_user_record: User,
) -> AsyncIterator[AsyncClient]:
    async for client in _client_for_user(
        session=session,
        settings=admin_settings,
        user=regular_user_record,
    ):
        yield client
