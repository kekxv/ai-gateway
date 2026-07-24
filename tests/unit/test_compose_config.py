from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[2]
BOOTSTRAP_NAMES = (
    "GATEWAY_BOOTSTRAP_ADMIN_EMAIL",
    "GATEWAY_BOOTSTRAP_ADMIN_PASSWORD",
    "GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET",
)


def compose_config(
    compose_file: str,
    tmp_path: Path,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    empty_env = tmp_path / "compose.env"
    empty_env.write_text("", encoding="utf-8")
    environment = os.environ.copy()
    for name in BOOTSTRAP_NAMES:
        environment.pop(name, None)
    environment.update(variables or {})
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(empty_env),
            "-f",
            compose_file,
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_root_compose_isolates_gateway_bootstrap_secrets(tmp_path: Path) -> None:
    config = compose_config(
        "compose.yaml",
        tmp_path,
        {
            "GATEWAY_BOOTSTRAP_ADMIN_EMAIL": "admin@example.test",
            "GATEWAY_BOOTSTRAP_ADMIN_PASSWORD": "secret-password",
            "GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
        },
    )
    services = config["services"]

    assert services["gateway"]["depends_on"]["setup"]["condition"] == (
        "service_completed_successfully"
    )
    assert {name: services["gateway"]["environment"][name] for name in BOOTSTRAP_NAMES} == {
        name: "" for name in BOOTSTRAP_NAMES
    }
    assert {name: services["setup"]["environment"][name] for name in BOOTSTRAP_NAMES} == {
        "GATEWAY_BOOTSTRAP_ADMIN_EMAIL": "admin@example.test",
        "GATEWAY_BOOTSTRAP_ADMIN_PASSWORD": "secret-password",
        "GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
    }


def test_example_compose_uses_complete_demo_defaults(tmp_path: Path) -> None:
    services = compose_config("example/compose.yaml", tmp_path)["services"]
    setup_environment = services["setup"]["environment"]
    setup_command = services["setup"]["command"][-1]

    assert setup_environment["GATEWAY_BOOTSTRAP_ADMIN_EMAIL"] == ""
    assert setup_environment["GATEWAY_BOOTSTRAP_ADMIN_PASSWORD"] == ""
    assert setup_environment["GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET"] == ""
    assert setup_environment["GATEWAY_BOOTSTRAP_ADMIN_OVERRIDE"] == ""
    assert "GATEWAY_BOOTSTRAP_ADMIN_EMAIL=admin@example.com" in setup_command
    assert "GATEWAY_BOOTSTRAP_ADMIN_PASSWORD=change-me-now" in setup_command
    assert "GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP" in setup_command
    assert BOOTSTRAP_NAMES[0] not in services["gateway"]["environment"]
    assert BOOTSTRAP_NAMES[1] not in services["gateway"]["environment"]
    assert BOOTSTRAP_NAMES[2] not in services["gateway"]["environment"]


@pytest.mark.parametrize(
    "variables",
    [
        {"GATEWAY_BOOTSTRAP_ADMIN_EMAIL": "custom@example.test"},
        {"GATEWAY_BOOTSTRAP_ADMIN_PASSWORD": "custom-password"},
    ],
)
def test_example_compose_partial_override_does_not_fall_back(
    tmp_path: Path,
    variables: dict[str, str],
) -> None:
    environment = compose_config("example/compose.yaml", tmp_path, variables)["services"]["setup"][
        "environment"
    ]

    assert environment["GATEWAY_BOOTSTRAP_ADMIN_OVERRIDE"]
    assert environment["GATEWAY_BOOTSTRAP_ADMIN_EMAIL"] == variables.get(
        "GATEWAY_BOOTSTRAP_ADMIN_EMAIL",
        "",
    )
    assert environment["GATEWAY_BOOTSTRAP_ADMIN_PASSWORD"] == variables.get(
        "GATEWAY_BOOTSTRAP_ADMIN_PASSWORD",
        "",
    )
    assert environment["GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET"] == ""


def test_example_compose_accepts_explicit_empty_totp_override(tmp_path: Path) -> None:
    environment = compose_config(
        "example/compose.yaml",
        tmp_path,
        {
            "GATEWAY_BOOTSTRAP_ADMIN_EMAIL": "custom@example.test",
            "GATEWAY_BOOTSTRAP_ADMIN_PASSWORD": "custom-password",
            "GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET": "",
        },
    )["services"]["setup"]["environment"]

    assert environment["GATEWAY_BOOTSTRAP_ADMIN_OVERRIDE"]
    assert environment["GATEWAY_BOOTSTRAP_ADMIN_EMAIL"] == "custom@example.test"
    assert environment["GATEWAY_BOOTSTRAP_ADMIN_PASSWORD"] == "custom-password"
    assert environment["GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET"] == ""
