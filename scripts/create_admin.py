from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ai_gateway.core.config import get_settings
from ai_gateway.core.security import hash_password
from ai_gateway.db.models import Account, User
from ai_gateway.db.session import get_engine_for_url, get_session_factory_for_engine


class AdminAlreadyExistsError(ValueError):
    pass


async def create_admin(email: str, password: str) -> User:
    normalized_email = email.strip()
    if len(normalized_email) < 3 or len(normalized_email) > 320:
        raise ValueError("email must contain between 3 and 320 characters")
    if not password:
        raise ValueError("password must not be empty")

    settings = get_settings()
    engine = get_engine_for_url(settings.database_url)
    session_factory = get_session_factory_for_engine(engine)
    try:
        async with session_factory() as session:
            if await session.scalar(select(User.id).where(User.email == normalized_email)):
                raise AdminAlreadyExistsError(f"user {normalized_email!r} already exists")
            admin = User(
                email=normalized_email,
                password_hash=hash_password(password),
                role="admin",
            )
            admin.account = Account()
            session.add(admin)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise AdminAlreadyExistsError(f"user {normalized_email!r} already exists") from None
            await session.refresh(admin)
            return admin
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the first gateway administrator")
    parser.add_argument("--email", required=True, help="administrator email address")
    parser.add_argument(
        "--password-env",
        metavar="NAME",
        help="read the password from environment variable NAME instead of prompting",
    )
    return parser.parse_args()


def password_from_args(args: argparse.Namespace) -> str:
    if args.password_env is not None:
        password = os.getenv(args.password_env)
        if not password:
            raise ValueError(f"environment variable {args.password_env!r} is missing or empty")
        return password
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("passwords do not match")
    return password


def main() -> int:
    args = parse_args()
    try:
        password = password_from_args(args)
        admin = asyncio.run(create_admin(args.email, password))
    except (AdminAlreadyExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created administrator {admin.email} (id={admin.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
