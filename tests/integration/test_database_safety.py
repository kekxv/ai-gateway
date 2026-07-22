from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ai_gateway.db.models import User
from ai_gateway.db.test_safety import UnsafeTestDatabaseError, assert_test_database_is_disposable


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
