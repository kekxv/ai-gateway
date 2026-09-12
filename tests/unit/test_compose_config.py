from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
BOOTSTRAP_NAMES = (
    "GATEWAY_BOOTSTRAP_ADMIN_EMAIL",
    "GATEWAY_BOOTSTRAP_ADMIN_PASSWORD",
    "GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET",
)
COMPOSE_REQUIRED_VARIABLES = {
    "MYSQL_DATABASE": "gateway",
    "MYSQL_TEST_DATABASE": "gateway_test",
    "MYSQL_USER": "gateway",
    "MYSQL_PASSWORD": "gateway-password",
    "MYSQL_ROOT_PASSWORD": "gateway-root-password",
    "GATEWAY_JWT_SECRET": "unit-test-jwt-secret",
    # A syntactically valid 32-byte Fernet key for config rendering tests.
    "GATEWAY_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "GATEWAY_ENVIRONMENT": "development",
}


def compose_config(
    compose_file: str,
    tmp_path: Path,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    empty_env = tmp_path / "compose.env"
    empty_env.write_text("", encoding="utf-8")
    environment = os.environ.copy()
    for name in (*BOOTSTRAP_NAMES, *COMPOSE_REQUIRED_VARIABLES):
        environment.pop(name, None)
    environment.update(COMPOSE_REQUIRED_VARIABLES)
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

    assert services["mysql"]["ports"] == [
        {
            "mode": "ingress",
            "host_ip": "127.0.0.1",
            "target": 3306,
            "published": "3306",
            "protocol": "tcp",
        }
    ]
    assert services["gateway"]["ports"][0]["host_ip"] == "127.0.0.1"
    for service in ("setup", "gateway"):
        assert (
            services[service]["environment"]["GATEWAY_JWT_SECRET"]
            == COMPOSE_REQUIRED_VARIABLES["GATEWAY_JWT_SECRET"]
        )
        assert (
            services[service]["environment"]["GATEWAY_ENCRYPTION_KEY"]
            == COMPOSE_REQUIRED_VARIABLES["GATEWAY_ENCRYPTION_KEY"]
        )

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


def test_root_compose_allows_bootstrap_variables_to_be_absent(tmp_path: Path) -> None:
    services = compose_config("compose.yaml", tmp_path)["services"]

    assert {name: services["setup"]["environment"][name] for name in BOOTSTRAP_NAMES} == {
        name: "" for name in BOOTSTRAP_NAMES
    }
    assert "--skip-if-all-empty" in services["setup"]["command"][-1]
    assert services["gateway"]["depends_on"]["setup"]["condition"] == (
        "service_completed_successfully"
    )


def test_example_compose_runs_migrations_without_bootstrap_credentials(tmp_path: Path) -> None:
    services = compose_config("example/compose.yaml", tmp_path)["services"]
    setup_command = services["setup"]["command"][-1]

    assert services["gateway"]["ports"][0]["host_ip"] == "127.0.0.1"
    for name in ("GATEWAY_JWT_SECRET", "GATEWAY_ENCRYPTION_KEY"):
        assert services["gateway"]["environment"][name] == COMPOSE_REQUIRED_VARIABLES[name]
    assert setup_command.strip() == "alembic upgrade head"
    assert all(name not in services["setup"]["environment"] for name in BOOTSTRAP_NAMES)
    assert all(name not in services["gateway"]["environment"] for name in BOOTSTRAP_NAMES)
    assert "create_admin.py" not in setup_command
    assert services["gateway"]["depends_on"]["setup"]["condition"] == (
        "service_completed_successfully"
    )
