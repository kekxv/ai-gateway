from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from ai_gateway.admin.bootstrap import AdminEmailConflictError, create_admin


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
        result = asyncio.run(create_admin(args.email, password))
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
