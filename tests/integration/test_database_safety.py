from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ai_gateway.db.models import User
from ai_gateway.db.test_safety import (
    UnsafeTestDatabaseError,
    assert_test_database_is_disposable,
    validate_test_database_url,
)


def test_database_guard_accepts_configured_gateway_test_schema(test_engine: AsyncEngine) -> None:
    database_url = test_engine.url.render_as_string(hide_password=False)

    assert (
        validate_test_database_url(
            database_url,
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway",
        )
        == "gateway_test"
    )


async def test_database_guard_rejects_preexisting_rows(test_engine: AsyncEngine) -> None:
    async with AsyncSession(test_engine, expire_on_commit=False) as setup:
        user = User(email=f"guard-{uuid4().hex}@example.com", password_hash="unused")
        setup.add(user)
        await setup.commit()
        user_id = user.id

    try:
        with pytest.raises(UnsafeTestDatabaseError, match="existing data"):
            await assert_test_database_is_disposable(test_engine)
    finally:
        async with AsyncSession(test_engine) as cleanup:
            user = await cleanup.get(User, user_id)
            if user is not None:
                await cleanup.delete(user)
                await cleanup.commit()
