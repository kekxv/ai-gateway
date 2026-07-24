from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Sequence

from ai_gateway.admin.bootstrap import AdminEmailConflictError, create_admin


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the first gateway administrator")
    email_source = parser.add_mutually_exclusive_group(required=True)
    email_source.add_argument("--email", help="administrator email address")
    email_source.add_argument(
        "--email-env",
        metavar="NAME",
        help="read the administrator email from environment variable NAME",
    )
    parser.add_argument(
        "--password-env",
        metavar="NAME",
        help="read the password from environment variable NAME instead of prompting",
    )
    parser.add_argument(
        "--totp-secret-env",
        metavar="NAME",
        help="read an optional Base32 TOTP secret from environment variable NAME",
    )
    parser.add_argument(
        "--skip-if-all-empty",
        action="store_true",
        help="skip creation when all configured bootstrap environment variables are empty",
    )
    return parser.parse_args(argv)


def required_environment_value(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"environment variable {name!r} is missing or empty")
    return value


def optional_environment_value(name: str) -> str | None:
    return os.getenv(name) or None


def email_from_args(args: argparse.Namespace) -> str:
    if args.email_env is not None:
        return required_environment_value(args.email_env)
    return str(args.email)


def password_from_args(args: argparse.Namespace) -> str:
    if args.password_env is not None:
        return required_environment_value(args.password_env)
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("passwords do not match")
    return password


def totp_secret_from_args(args: argparse.Namespace) -> str | None:
    if args.totp_secret_env is None:
        return None
    return optional_environment_value(args.totp_secret_env)


def bootstrap_values_from_args(args: argparse.Namespace) -> tuple[str, str, str | None] | None:
    if args.skip_if_all_empty and (args.email_env is None or args.password_env is None):
        raise ValueError("--skip-if-all-empty requires --email-env and --password-env")

    if args.email_env is not None and args.password_env is not None:
        email = optional_environment_value(args.email_env)
        password = optional_environment_value(args.password_env)
        totp_secret = totp_secret_from_args(args)
        if args.skip_if_all_empty and email is None and password is None and totp_secret is None:
            return None
        if email is None or password is None:
            raise ValueError("bootstrap administrator email and password must both be configured")
        return email, password, totp_secret

    return email_from_args(args), password_from_args(args), totp_secret_from_args(args)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        values = bootstrap_values_from_args(args)
        if values is None:
            print("bootstrap administrator is not configured; skipping")
            return 0
        email, password, totp_secret = values
        result = asyncio.run(create_admin(email, password, totp_secret=totp_secret))
    except (AdminEmailConflictError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if result.created:
        print(f"created administrator {result.user.email} (id={result.user.id})")
    else:
        print(f"administrator {result.user.email} already exists; no changes made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
