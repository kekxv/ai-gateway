from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _load_create_admin_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "create_admin.py"
    spec = importlib.util.spec_from_file_location("create_admin_script", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


create_admin = _load_create_admin_script()


def test_parse_args_accepts_email_and_secret_environment_names() -> None:
    args = create_admin.parse_args(
        [
            "--email-env",
            "ADMIN_EMAIL",
            "--password-env",
            "ADMIN_PASSWORD",
            "--totp-secret-env",
            "ADMIN_TOTP_SECRET",
        ]
    )

    assert args.email_env == "ADMIN_EMAIL"
    assert args.password_env == "ADMIN_PASSWORD"
    assert args.totp_secret_env == "ADMIN_TOTP_SECRET"


def test_parse_args_rejects_both_email_sources() -> None:
    with pytest.raises(SystemExit):
        create_admin.parse_args(["--email", "admin@example.test", "--email-env", "ADMIN_EMAIL"])


@pytest.mark.parametrize("value", [None, ""])
def test_required_environment_value_rejects_missing_or_empty(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    name = "BOOTSTRAP_SECRET"
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match="missing or empty"):
        create_admin.required_environment_value(name)


def test_email_and_totp_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("ADMIN_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    args = argparse.Namespace(
        email=None,
        email_env="ADMIN_EMAIL",
        totp_secret_env="ADMIN_TOTP_SECRET",
    )

    assert create_admin.email_from_args(args) == "admin@example.test"
    assert create_admin.totp_secret_from_args(args) == "JBSWY3DPEHPK3PXP"


def test_totp_is_optional_when_no_environment_name_is_requested() -> None:
    args = argparse.Namespace(totp_secret_env=None)

    assert create_admin.totp_secret_from_args(args) is None


def _environment_args(*extra: str) -> argparse.Namespace:
    return create_admin.parse_args(
        [
            "--email-env",
            "ADMIN_EMAIL",
            "--password-env",
            "ADMIN_PASSWORD",
            "--totp-secret-env",
            "ADMIN_TOTP_SECRET",
            *extra,
        ]
    )


def test_skip_if_all_bootstrap_environment_values_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("ADMIN_EMAIL", "ADMIN_PASSWORD", "ADMIN_TOTP_SECRET"):
        monkeypatch.setenv(name, "")

    assert create_admin.bootstrap_values_from_args(_environment_args("--skip-if-all-empty")) is None


@pytest.mark.parametrize(
    ("email", "password"),
    [("admin@example.test", ""), ("", "strong-password")],
)
def test_partial_bootstrap_environment_fails(
    monkeypatch: pytest.MonkeyPatch,
    email: str,
    password: str,
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", email)
    monkeypatch.setenv("ADMIN_PASSWORD", password)
    monkeypatch.setenv("ADMIN_TOTP_SECRET", "")

    with pytest.raises(ValueError, match="email and password must both"):
        create_admin.bootstrap_values_from_args(_environment_args("--skip-if-all-empty"))


def test_empty_totp_environment_disables_totp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-password")
    monkeypatch.setenv("ADMIN_TOTP_SECRET", "")

    assert create_admin.bootstrap_values_from_args(_environment_args()) == (
        "admin@example.test",
        "strong-password",
        None,
    )


def test_main_reads_bootstrap_values_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-password")
    monkeypatch.setenv("ADMIN_TOTP_SECRET", secret)
    received: list[tuple[str, str, str | None]] = []

    async def fake_create_admin(
        email: str,
        password: str,
        *,
        totp_secret: str | None,
    ) -> SimpleNamespace:
        received.append((email, password, totp_secret))
        return SimpleNamespace(
            created=True,
            user=SimpleNamespace(email=email, id=1),
        )

    monkeypatch.setattr(create_admin, "create_admin", fake_create_admin)

    assert (
        create_admin.main(
            [
                "--email-env",
                "ADMIN_EMAIL",
                "--password-env",
                "ADMIN_PASSWORD",
                "--totp-secret-env",
                "ADMIN_TOTP_SECRET",
            ]
        )
        == 0
    )
    assert received == [("admin@example.test", "strong-password", secret)]
    assert secret not in capsys.readouterr().out
