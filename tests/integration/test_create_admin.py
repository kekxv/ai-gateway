from __future__ import annotations

import asyncio
from uuid import uuid4

import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_gateway.admin import bootstrap as create_admin_module
from ai_gateway.admin.bootstrap import AdminEmailConflictError, create_admin
from ai_gateway.core.config import Settings
from ai_gateway.core.security import decrypt_secret, hash_password, verify_password
from ai_gateway.db.models import Account, User


async def _delete_user(sessions: async_sessionmaker[AsyncSession], email: str) -> None:
    async with sessions() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            return
        await session.execute(delete(Account).where(Account.user_id == user.id))
        await session.delete(user)
        await session.commit()


async def test_create_admin_creates_user_and_account(test_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-{uuid4().hex}@example.test"

    try:
        result = await create_admin(email, "first-password", session_factory=sessions)

        assert result.created is True
        assert result.user.email == email
        assert result.user.role == "admin"
        async with sessions() as session:
            stored = await session.scalar(select(User).where(User.email == email))
            assert stored is not None
            assert stored.role == "admin"
            assert stored.totp_enabled is False
            assert stored.totp_secret_encrypted is None
            assert verify_password("first-password", stored.password_hash)
            assert await session.scalar(select(Account).where(Account.user_id == stored.id))
    finally:
        await _delete_user(sessions, email)


async def test_create_admin_enables_encrypted_totp_for_new_user(
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-totp-{uuid4().hex}@example.test"
    secret = pyotp.random_base32()
    settings = Settings(
        environment="test",
        jwt_secret="integration-test-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr(create_admin_module, "get_settings", lambda: settings)

    try:
        result = await create_admin(
            email,
            "first-password",
            totp_secret=secret,
            session_factory=sessions,
        )

        assert result.created is True
        async with sessions() as session:
            stored = await session.scalar(select(User).where(User.email == email))
            assert stored is not None
            assert stored.totp_enabled is True
            assert stored.totp_secret_encrypted is not None
            assert secret.encode() not in stored.totp_secret_encrypted
            assert decrypt_secret(stored.totp_secret_encrypted, settings=settings) == secret
    finally:
        await _delete_user(sessions, email)


async def test_create_admin_is_noop_for_existing_admin(test_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-existing-{uuid4().hex}@example.test"

    try:
        created = await create_admin(email, "original-password", session_factory=sessions)
        duplicate = await create_admin(email, "replacement-password", session_factory=sessions)

        assert created.created is True
        assert duplicate.created is False
        assert duplicate.user.id == created.user.id
        async with sessions() as session:
            stored = await session.scalar(select(User).where(User.email == email))
            assert stored is not None
            assert stored.role == "admin"
            assert verify_password("original-password", stored.password_hash)
            assert not verify_password("replacement-password", stored.password_hash)
    finally:
        await _delete_user(sessions, email)


async def test_create_admin_does_not_replace_existing_password_or_totp(
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-existing-totp-{uuid4().hex}@example.test"
    original_secret = pyotp.random_base32()
    replacement_secret = pyotp.random_base32()
    settings = Settings(
        environment="test",
        jwt_secret="integration-test-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr(create_admin_module, "get_settings", lambda: settings)

    try:
        created = await create_admin(
            email,
            "original-password",
            totp_secret=original_secret,
            session_factory=sessions,
        )
        original_ciphertext = created.user.totp_secret_encrypted
        duplicate = await create_admin(
            email,
            "replacement-password",
            totp_secret=replacement_secret,
            session_factory=sessions,
        )

        assert duplicate.created is False
        async with sessions() as session:
            stored = await session.scalar(select(User).where(User.email == email))
            assert stored is not None
            assert verify_password("original-password", stored.password_hash)
            assert not verify_password("replacement-password", stored.password_hash)
            assert stored.totp_enabled is True
            assert stored.totp_secret_encrypted == original_ciphertext
            assert (
                decrypt_secret(stored.totp_secret_encrypted, settings=settings) == original_secret
            )
    finally:
        await _delete_user(sessions, email)


async def test_create_admin_does_not_validate_new_values_for_existing_admin(
    test_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-existing-invalid-{uuid4().hex}@example.test"

    try:
        created = await create_admin(email, "original-password", session_factory=sessions)
        duplicate = await create_admin(
            email,
            "",
            totp_secret="not a base32 secret!",
            session_factory=sessions,
        )

        assert created.created is True
        assert duplicate.created is False
        async with sessions() as session:
            stored = await session.scalar(select(User).where(User.email == email))
            assert stored is not None
            assert verify_password("original-password", stored.password_hash)
            assert stored.totp_enabled is False
            assert stored.totp_secret_encrypted is None
    finally:
        await _delete_user(sessions, email)


async def test_create_admin_rejects_invalid_totp_for_new_user(test_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-invalid-totp-{uuid4().hex}@example.test"

    with pytest.raises(ValueError, match="valid Base32"):
        await create_admin(
            email,
            "first-password",
            totp_secret="not a base32 secret!",
            session_factory=sessions,
        )

    async with sessions() as session:
        assert await session.scalar(select(User).where(User.email == email)) is None


async def test_create_admin_rejects_short_totp_for_new_user(test_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-short-totp-{uuid4().hex}@example.test"

    with pytest.raises(ValueError, match="at least 20 bytes"):
        await create_admin(
            email,
            "first-password",
            totp_secret="JBSWY3DPEHPK3PXP",
            session_factory=sessions,
        )

    async with sessions() as session:
        assert await session.scalar(select(User).where(User.email == email)) is None


async def test_create_admin_rejects_existing_regular_user(test_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-user-{uuid4().hex}@example.test"
    async with sessions() as session:
        regular = User(
            email=email,
            password_hash=hash_password("regular-password"),
            role="user",
            account=Account(),
        )
        session.add(regular)
        await session.commit()

    try:
        with pytest.raises(AdminEmailConflictError, match="regular user"):
            await create_admin(email, "admin-password", session_factory=sessions)

        async with sessions() as session:
            stored = await session.scalar(select(User).where(User.email == email))
            assert stored is not None
            assert stored.role == "user"
            assert verify_password("regular-password", stored.password_hash)
    finally:
        await _delete_user(sessions, email)


async def test_create_admin_race_rereads_integrity_conflict(
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    email = f"bootstrap-race-{uuid4().hex}@example.test"
    original_load_user = create_admin_module._load_user
    entrants = 0
    lock = asyncio.Lock()
    ready = asyncio.Event()
    passwords = ("first-race-password", "second-race-password")
    secrets = (pyotp.random_base32(), pyotp.random_base32())
    settings = Settings(
        environment="test",
        jwt_secret="integration-test-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )

    async def synchronized_load_user(session: AsyncSession, candidate: str) -> User | None:
        nonlocal entrants
        user = await original_load_user(session, candidate)
        if user is not None:
            return user
        async with lock:
            entrants += 1
            if entrants == 2:
                ready.set()
        if entrants <= 2:
            await asyncio.wait_for(ready.wait(), timeout=2)
        return None

    monkeypatch.setattr(create_admin_module, "_load_user", synchronized_load_user)
    monkeypatch.setattr(create_admin_module, "get_settings", lambda: settings)

    try:
        first, second = await asyncio.gather(
            create_admin(
                email,
                passwords[0],
                totp_secret=secrets[0],
                session_factory=sessions,
            ),
            create_admin(
                email,
                passwords[1],
                totp_secret=secrets[1],
                session_factory=sessions,
            ),
        )

        assert sorted((first.created, second.created)) == [False, True]
        assert first.user.id == second.user.id
        winner = 0 if first.created else 1
        loser = 1 - winner
        async with sessions() as session:
            users = list(await session.scalars(select(User).where(User.email == email)))
            assert len(users) == 1
            assert users[0].role == "admin"
            assert verify_password(passwords[winner], users[0].password_hash)
            assert not verify_password(passwords[loser], users[0].password_hash)
            assert users[0].totp_enabled is True
            assert users[0].totp_secret_encrypted is not None
            assert (
                decrypt_secret(users[0].totp_secret_encrypted, settings=settings) == secrets[winner]
            )
    finally:
        await _delete_user(sessions, email)
