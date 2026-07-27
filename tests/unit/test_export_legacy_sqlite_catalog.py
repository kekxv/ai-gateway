from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


def _exporter_module():
    script_path = Path(__file__).parents[2] / "scripts" / "export_legacy_sqlite_catalog.py"
    specification = importlib.util.spec_from_file_location("legacy_catalog_exporter", script_path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _legacy_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE "User" (id INTEGER PRIMARY KEY, email TEXT NOT NULL);
        CREATE TABLE "Provider" (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, "baseURL" TEXT NOT NULL,
            "apiKey" TEXT, type TEXT, types TEXT, "autoLoadModels" INTEGER,
            disabled INTEGER NOT NULL DEFAULT 0, "userId" INTEGER
        );
        CREATE TABLE "ProviderType" (
            "providerId" INTEGER NOT NULL, type TEXT NOT NULL, "baseURL" TEXT NOT NULL
        );
        CREATE TABLE "Channel" (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, "userId" INTEGER,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE "ChannelProvider" (
            "channelId" INTEGER NOT NULL, "providerId" INTEGER NOT NULL
        );
        CREATE TABLE "ChannelAllowedModel" (
            "channelId" INTEGER NOT NULL, "modelId" INTEGER NOT NULL
        );
        CREATE TABLE "GatewayApiKey" (id INTEGER PRIMARY KEY, "userId" INTEGER);
        CREATE TABLE "GatewayApiKeyChannel" (
            "apiKeyId" INTEGER NOT NULL, "channelId" INTEGER NOT NULL
        );
        CREATE TABLE "Model" (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, alias TEXT, "inputTokenPrice" INTEGER,
            "outputTokenPrice" INTEGER, "userId" INTEGER
        );
        CREATE TABLE "ModelAlias" ("modelId" INTEGER NOT NULL, alias TEXT NOT NULL);
        CREATE TABLE "ModelRoute" (
            id INTEGER PRIMARY KEY, "modelId" INTEGER NOT NULL, "providerId" INTEGER NOT NULL,
            weight INTEGER NOT NULL, disabled INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    connection.executemany(
        'INSERT INTO "User" VALUES (?, ?)',
        [(1, "selected@example.test"), (2, "other@example.test")],
    )
    connection.executemany(
        'INSERT INTO "Provider" (id, name, "baseURL", disabled, "userId") VALUES (?, ?, ?, ?, ?)',
        [
            (10, "selected-provider", "https://selected.example/v1", 0, None),
            (20, "other-provider", "https://other.example/v1", 0, None),
        ],
    )
    connection.executemany(
        'INSERT INTO "Channel" (id, name, "userId", enabled) VALUES (?, ?, ?, ?)',
        [(100, "selected-channel", 1, 1), (200, "other-channel", 2, 1)],
    )
    connection.executemany(
        'INSERT INTO "ChannelProvider" VALUES (?, ?)',
        [(100, 10), (200, 20)],
    )
    connection.executemany(
        (
            'INSERT INTO "Model" (id, name, alias, "inputTokenPrice", '
            '"outputTokenPrice", "userId") '
            "VALUES (?, ?, ?, ?, ?, ?)"
        ),
        [
            (1000, "selected-channel-model", "selected-alias", 0, 0, None),
            (1001, "selected-direct-model", None, 0, 0, 1),
            (2000, "other-model", None, 0, 0, None),
        ],
    )
    connection.executemany(
        'INSERT INTO "ChannelAllowedModel" VALUES (?, ?)',
        [(100, 1000), (200, 2000)],
    )
    connection.executemany(
        (
            'INSERT INTO "ModelRoute" (id, "modelId", "providerId", weight, disabled) '
            "VALUES (?, ?, ?, ?, ?)"
        ),
        [(1, 1000, 10, 10, 0), (2, 2000, 20, 10, 0)],
    )
    connection.commit()
    connection.close()


def test_exports_only_selected_user_catalog_graph(tmp_path: Path) -> None:
    """Removing user-graph traversal would leak another user's catalog records."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)

    bundle = _exporter_module().export_legacy_catalog(
        database_path, "selected@example.test", include_unowned=False, include_secrets=False
    )

    assert [provider["name"] for provider in bundle["providers"]] == ["selected-provider"]
    assert [model["canonical_name"] for model in bundle["models"]] == [
        "selected-channel-model",
        "selected-direct-model",
    ]
    assert "channels" not in bundle
    assert "api_keys" not in bundle


def test_exports_legacy_prices_and_default_multipliers(tmp_path: Path) -> None:
    """Changing the legacy tenths-of-a-cent conversion would misprice imported models."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        'UPDATE "Model" SET "inputTokenPrice" = 30, "outputTokenPrice" = 60 WHERE id = 1001'
    )
    connection.commit()
    connection.close()

    bundle = _exporter_module().export_legacy_catalog(
        database_path, "1", include_unowned=False, include_secrets=False
    )
    model = next(
        item for item in bundle["models"] if item["canonical_name"] == "selected-direct-model"
    )

    assert model["input_price_per_million"] == "3"
    assert model["output_price_per_million"] == "6"
    assert model["cache_read_price_per_million"] == "0"
    assert model["cache_write_price_per_million"] == "0"
    assert model["price_multiplier"] == "1.00"
    assert bundle["providers"][0]["price_multiplier"] == "1.00"


@pytest.mark.parametrize(
    ("source_price", "expected_price"),
    [(100, "10"), (300, "30"), (1000, "100")],
)
def test_legacy_integer_prices_keep_significant_trailing_zeros(
    source_price: int,
    expected_price: str,
) -> None:
    """Trimming the integer portion would reduce common legacy prices by powers of ten."""

    assert _exporter_module()._legacy_price(source_price) == expected_price


def test_exports_provider_protocols_with_legacy_fallbacks_and_deduplication(tmp_path: Path) -> None:
    """Ignoring type precedence or duplicates creates invalid provider protocol configurations."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.executemany(
        (
            'INSERT INTO "Provider" (id, name, "baseURL", type, types, disabled, "userId") '
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        ),
        [
            (11, "json-types", "https://json.example", None, '["gemini", "anthropic"]', 0, 1),
            (12, "deprecated-type", "https://type.example", "openai", None, 0, 1),
            (13, "default-type", "https://default.example", None, None, 0, 1),
        ],
    )
    connection.executemany(
        'INSERT INTO "ProviderType" ("providerId", type, "baseURL") VALUES (?, ?, ?)',
        [
            (10, "anthropic", "https://claude.example"),
            (10, "anthropic", "https://claude.example"),
            (10, "openai", "https://selected.example/v1"),
        ],
    )
    connection.commit()
    connection.close()

    bundle = _exporter_module().export_legacy_catalog(
        database_path, "1", include_unowned=False, include_secrets=False
    )
    providers = {provider["name"]: provider for provider in bundle["providers"]}

    assert providers["selected-provider"]["protocols"] == [
        {
            "protocol": "claude",
            "base_url": "https://claude.example",
            "websocket_url": None,
            "extra_headers": None,
            "supports_responses": True,
            "enabled": True,
        },
        {
            "protocol": "openai",
            "base_url": "https://selected.example/v1",
            "websocket_url": None,
            "extra_headers": None,
            "supports_responses": True,
            "enabled": True,
        },
    ]
    assert [protocol["protocol"] for protocol in providers["json-types"]["protocols"]] == [
        "claude",
        "gemini",
    ]
    assert providers["deprecated-type"]["protocols"][0]["protocol"] == "openai"
    assert providers["default-type"]["protocols"][0]["protocol"] == "openai"


def test_redacts_provider_secrets_unless_explicitly_requested(tmp_path: Path) -> None:
    """Returning legacy API keys without opt-in would expose upstream credentials."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute('UPDATE "Provider" SET "apiKey" = ? WHERE id = 10', ("legacy-secret",))
    connection.commit()
    connection.close()
    exporter = _exporter_module()

    redacted = exporter.export_legacy_catalog(database_path, "1", False, False)
    with_secrets = exporter.export_legacy_catalog(database_path, "1", False, True)

    assert redacted["providers"][0]["credential"] is None
    assert with_secrets["providers"][0]["credential"] == {"api_key": "legacy-secret"}


def test_includes_unowned_legacy_records_only_with_opt_in(tmp_path: Path) -> None:
    """Treating global legacy records as personal data leaks records unless explicitly requested."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        'INSERT INTO "Provider" (id, name, "baseURL", disabled, "userId") VALUES (?, ?, ?, ?, ?)',
        (99, "unowned-provider", "https://unowned.example", 0, None),
    )
    connection.execute(
        (
            'INSERT INTO "Model" (id, name, "inputTokenPrice", "outputTokenPrice", "userId") '
            "VALUES (?, ?, ?, ?, ?)"
        ),
        (999, "unowned-model", 0, 0, None),
    )
    connection.commit()
    connection.close()
    exporter = _exporter_module()

    default_bundle = exporter.export_legacy_catalog(database_path, "1", False, False)
    unowned_bundle = exporter.export_legacy_catalog(database_path, "1", True, False)

    assert "unowned-provider" not in [provider["name"] for provider in default_bundle["providers"]]
    assert "unowned-model" not in [model["canonical_name"] for model in default_bundle["models"]]
    assert "unowned-provider" in [provider["name"] for provider in unowned_bundle["providers"]]
    assert "unowned-model" in [model["canonical_name"] for model in unowned_bundle["models"]]


def test_include_unowned_follows_channels_bound_to_an_unowned_api_key(tmp_path: Path) -> None:
    """Ignoring an unowned API key's bindings loses the catalog graph that key actually exposes."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute('UPDATE "Provider" SET "userId" = 2 WHERE id = 20')
    connection.execute('UPDATE "Model" SET "userId" = 2 WHERE id = 2000')
    connection.execute('INSERT INTO "GatewayApiKey" (id, "userId") VALUES (?, ?)', (7, None))
    connection.execute('INSERT INTO "GatewayApiKeyChannel" VALUES (?, ?)', (7, 200))
    connection.commit()
    connection.close()

    bundle = _exporter_module().export_legacy_catalog(database_path, "1", True, False)

    assert "other-provider" in [provider["name"] for provider in bundle["providers"]]
    assert "other-model" in [model["canonical_name"] for model in bundle["models"]]


def test_deduplicates_model_aliases_but_rejects_cross_model_alias_conflicts(tmp_path: Path) -> None:
    """Allowing an alias to resolve to two imported models makes model routing ambiguous."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.executemany(
        'INSERT INTO "ModelAlias" ("modelId", alias) VALUES (?, ?)',
        [(1001, "fast"), (1001, "fast"), (1000, "fast")],
    )
    connection.commit()
    connection.close()
    exporter = _exporter_module()

    with pytest.raises(exporter.LegacyExportError, match="Alias .*fast"):
        exporter.export_legacy_catalog(database_path, "1", False, False)

    connection = sqlite3.connect(database_path)
    connection.execute('DELETE FROM "ModelAlias" WHERE "modelId" = 1000 AND alias = ?', ("fast",))
    connection.commit()
    connection.close()
    bundle = exporter.export_legacy_catalog(database_path, "1", False, False)
    model = next(
        item for item in bundle["models"] if item["canonical_name"] == "selected-direct-model"
    )

    assert model["aliases"] == [{"alias": "fast", "enabled": True}]


def test_exports_valid_routes_with_legacy_model_name_and_rejects_invalid_weight(
    tmp_path: Path,
) -> None:
    """Silently clamping legacy route weights changes traffic allocation during migration."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    exporter = _exporter_module()

    bundle = exporter.export_legacy_catalog(database_path, "1", False, False)
    route = bundle["models"][0]["routes"][0]

    assert route["upstream_model"] == "selected-channel-model"
    assert route["enabled"] is True
    assert route["weight"] == 10

    connection = sqlite3.connect(database_path)
    connection.execute('UPDATE "ModelRoute" SET weight = 0, disabled = 1 WHERE id = 1')
    connection.commit()
    connection.close()

    with pytest.raises(exporter.LegacyExportError, match="weight"):
        exporter.export_legacy_catalog(database_path, "1", False, False)


def test_rejects_duplicate_selected_provider_names(tmp_path: Path) -> None:
    """Duplicate provider names make route targets ambiguous in the v1 bundle."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        'INSERT INTO "Provider" (id, name, "baseURL", disabled, "userId") VALUES (?, ?, ?, ?, ?)',
        (11, "selected-provider", "https://second.example/v1", 0, 1),
    )
    connection.commit()
    connection.close()

    exporter = _exporter_module()

    with pytest.raises(exporter.LegacyExportError, match="Duplicate provider name"):
        exporter.export_legacy_catalog(database_path, "1", False, False)


def test_rejects_alias_equal_to_another_selected_model_canonical_name(tmp_path: Path) -> None:
    """An alias matching a canonical name makes the Task 1 import catalog ambiguous."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        'INSERT INTO "ModelAlias" ("modelId", alias) VALUES (?, ?)',
        (1000, "selected-direct-model"),
    )
    connection.commit()
    connection.close()

    exporter = _exporter_module()

    with pytest.raises(exporter.LegacyExportError, match="Alias conflict"):
        exporter.export_legacy_catalog(database_path, "1", False, False)


def test_rejects_unsupported_legacy_provider_protocol(tmp_path: Path) -> None:
    """A protocol outside the Task 1 enum would make the exported bundle unimportable."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute('UPDATE "Provider" SET types = ? WHERE id = 10', ('["azure"]',))
    connection.commit()
    connection.close()

    exporter = _exporter_module()

    with pytest.raises(exporter.LegacyExportError, match="Unsupported provider protocol"):
        exporter.export_legacy_catalog(database_path, "1", False, False)


@pytest.mark.parametrize("non_finite_price", ["NaN", "Infinity"])
def test_rejects_non_finite_legacy_prices(tmp_path: Path, non_finite_price: str) -> None:
    """Non-finite prices cannot be represented by the Task 1 decimal price contract."""
    database_path = tmp_path / "legacy.sqlite"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        'UPDATE "Model" SET "inputTokenPrice" = ? WHERE id = 1001', (non_finite_price,)
    )
    connection.commit()
    connection.close()

    exporter = _exporter_module()

    with pytest.raises(exporter.LegacyExportError, match="Invalid legacy token price"):
        exporter.export_legacy_catalog(database_path, "1", False, False)


def test_cli_reports_non_finite_legacy_price_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed non-finite price data must return CLI exit 1 rather than a Decimal traceback."""
    database_path = tmp_path / "legacy.sqlite"
    output_path = tmp_path / "catalog.json"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute('UPDATE "Model" SET "inputTokenPrice" = ? WHERE id = 1001', ("NaN",))
    connection.commit()
    connection.close()

    result = _exporter_module().main(
        [str(database_path), "--user", "1", "--output", str(output_path)]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Invalid legacy token price" in captured.err
    assert "Traceback" not in captured.err
    assert not output_path.exists()


def test_cli_writes_private_catalog_output_without_printing_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Writing a world-readable backup or echoing its credentials exposes upstream secrets."""
    database_path = tmp_path / "legacy.sqlite"
    output_path = tmp_path / "catalog.json"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute('UPDATE "Provider" SET "apiKey" = ? WHERE id = 10', ("legacy-secret",))
    connection.commit()
    connection.close()

    result = _exporter_module().main(
        [
            str(database_path),
            "--user",
            "1",
            "--output",
            str(output_path),
            "--include-secrets",
        ]
    )

    assert result == 0
    output_bundle = json.loads(output_path.read_text())
    assert output_bundle["providers"][0]["credential"] == {"api_key": "legacy-secret"}
    assert output_path.stat().st_mode & 0o777 == 0o600
    captured = capsys.readouterr()
    assert "Exported 1 provider(s) and 2 model(s)" in captured.out
    assert "legacy-secret" not in captured.out
    assert captured.err == ""


def test_cli_requires_force_before_replacing_an_existing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Replacing a backup without confirmation destroys the previous catalog export."""
    database_path = tmp_path / "legacy.sqlite"
    output_path = tmp_path / "catalog.json"
    _legacy_database(database_path)
    output_path.write_text("existing backup")

    result = _exporter_module().main(
        [str(database_path), "--user", "1", "--output", str(output_path)]
    )

    assert result == 1
    assert output_path.read_text() == "existing backup"
    assert "already exists" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("prepare", "expected_error"),
    [
        (lambda path: None, "User not found"),
        (lambda path: path.write_text("not sqlite"), "Cannot open legacy database"),
    ],
)
def test_cli_reports_unknown_user_and_invalid_database_concisely(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    prepare,
    expected_error: str,
) -> None:
    """CLI errors must be actionable without dumping a traceback or catalog contents."""
    database_path = tmp_path / "legacy.sqlite"
    output_path = tmp_path / "catalog.json"
    _legacy_database(database_path)
    prepare(database_path)
    user = "missing@example.test" if expected_error == "User not found" else "1"

    result = _exporter_module().main(
        [str(database_path), "--user", user, "--output", str(output_path)]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert expected_error in captured.err
    assert "Traceback" not in captured.err
    assert not output_path.exists()


def test_cli_reports_malformed_legacy_json_without_writing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed provider type JSON must stop export rather than produce a partial catalog."""
    database_path = tmp_path / "legacy.sqlite"
    output_path = tmp_path / "catalog.json"
    _legacy_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute('UPDATE "Provider" SET types = ? WHERE id = 10', ("{",))
    connection.commit()
    connection.close()

    result = _exporter_module().main(
        [str(database_path), "--user", "1", "--output", str(output_path)]
    )

    assert result == 1
    assert "Invalid JSON" in capsys.readouterr().err
    assert not output_path.exists()


def test_cli_atomic_output_removes_its_temporary_file_when_serialization_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A serialization failure must not leave a partially written final or temporary backup."""
    database_path = tmp_path / "legacy.sqlite"
    output_path = tmp_path / "catalog.json"
    _legacy_database(database_path)
    exporter = _exporter_module()

    def fail_serialization(*_args, **_kwargs):
        raise OSError("simulated serialization failure")

    monkeypatch.setattr(exporter.json, "dumps", fail_serialization)
    result = exporter.main([str(database_path), "--user", "1", "--output", str(output_path)])

    assert result == 1
    assert not output_path.exists()
    assert list(tmp_path.glob(".catalog.json.*")) == []
