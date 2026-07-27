from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from urllib.parse import quote


class LegacyExportError(Exception):
    """The legacy database cannot be exported safely."""


CORE_TABLES = frozenset({"User", "Provider", "Model"})


def export_legacy_catalog(
    database_path: str | Path,
    user_selector: str,
    include_unowned: bool,
    include_secrets: bool,
) -> dict[str, object]:
    connection = _open_database(database_path)
    try:
        tables = _table_names(connection)
        missing_tables = CORE_TABLES - tables
        if missing_tables:
            raise LegacyExportError(
                f"Legacy database is missing required table(s): {', '.join(sorted(missing_tables))}"
            )
        user_id = _resolve_user_id(connection, user_selector)
        selected_channels = _selected_channels(connection, tables, user_id, include_unowned)
        selected_provider_ids = _selected_ids(
            connection,
            tables,
            "Provider",
            selected_channels,
            "ChannelProvider",
            user_id,
            include_unowned,
        )
        selected_model_ids = _selected_ids(
            connection,
            tables,
            "Model",
            selected_channels,
            "ChannelAllowedModel",
            user_id,
            include_unowned,
        )
        providers = _providers(connection, tables, selected_provider_ids, include_secrets)
        models = _models(
            connection,
            tables,
            selected_model_ids,
            {str(provider["name"]): provider for provider in providers},
        )
        return {
            "format": "ai-gateway.catalog",
            "version": 1,
            "providers": providers,
            "models": models,
        }
    except sqlite3.Error as error:
        raise LegacyExportError(f"Cannot open legacy database: {error}") from error
    finally:
        connection.close()


def _open_database(database_path: str | Path) -> sqlite3.Connection:
    resolved_path = Path(database_path).resolve()
    uri = f"file:{quote(str(resolved_path), safe='/')}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise LegacyExportError(f"Cannot open legacy database: {error}") from error
    connection.row_factory = sqlite3.Row
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _resolve_user_id(connection: sqlite3.Connection, user_selector: str) -> int:
    if user_selector.isdecimal():
        row = connection.execute(
            'SELECT id FROM "User" WHERE id = ?', (int(user_selector),)
        ).fetchone()
    else:
        row = connection.execute(
            'SELECT id FROM "User" WHERE email = ?', (user_selector,)
        ).fetchone()
    if row is None:
        raise LegacyExportError(f"User not found: {user_selector}")
    return int(row["id"])


def _selected_channels(
    connection: sqlite3.Connection,
    tables: set[str],
    user_id: int,
    include_unowned: bool,
) -> set[int]:
    if "Channel" not in tables:
        return set()
    rows = connection.execute('SELECT id, "userId" FROM "Channel"').fetchall()
    channel_ids = {int(row["id"]) for row in rows if row["userId"] == user_id}
    if include_unowned:
        channel_ids.update(int(row["id"]) for row in rows if row["userId"] is None)
    if {"GatewayApiKey", "GatewayApiKeyChannel"} <= tables:
        user_condition = 'api_key."userId" = ?'
        if include_unowned:
            user_condition += ' OR api_key."userId" IS NULL'
        channel_ids.update(
            int(row["channelId"])
            for row in connection.execute(
                f"""
                SELECT association."channelId"
                FROM "GatewayApiKeyChannel" AS association
                JOIN "GatewayApiKey" AS api_key ON api_key.id = association."apiKeyId"
                WHERE {user_condition}
                """,
                (user_id,),
            )
        )
    return channel_ids


def _selected_ids(
    connection: sqlite3.Connection,
    tables: set[str],
    table: str,
    channel_ids: set[int],
    association_table: str,
    user_id: int,
    include_unowned: bool,
) -> set[int]:
    rows = connection.execute(f'SELECT id, "userId" FROM "{table}"').fetchall()
    selected = {int(row["id"]) for row in rows if row["userId"] == user_id}
    if include_unowned:
        selected.update(int(row["id"]) for row in rows if row["userId"] is None)
    if channel_ids and association_table in tables:
        id_column = "providerId" if table == "Provider" else "modelId"
        placeholders = ", ".join("?" for _ in channel_ids)
        selected.update(
            int(row[id_column])
            for row in connection.execute(
                f'SELECT "{id_column}" FROM "{association_table}" '
                f'WHERE "channelId" IN ({placeholders})',
                tuple(sorted(channel_ids)),
            )
        )
    return selected


def _providers(
    connection: sqlite3.Connection,
    tables: set[str],
    provider_ids: set[int],
    include_secrets: bool,
) -> list[dict[str, object]]:
    if not provider_ids:
        return []
    placeholders = ", ".join("?" for _ in provider_ids)
    rows = connection.execute(
        f'SELECT * FROM "Provider" WHERE id IN ({placeholders}) ORDER BY name, id',
        tuple(sorted(provider_ids)),
    ).fetchall()
    return [_provider(connection, tables, row, include_secrets) for row in rows]


def _provider(
    connection: sqlite3.Connection,
    tables: set[str],
    row: sqlite3.Row,
    include_secrets: bool,
) -> dict[str, object]:
    enabled = not bool(row["disabled"])
    return {
        "name": str(row["name"]),
        "credential": {"api_key": row["apiKey"]} if include_secrets and row["apiKey"] else None,
        "enabled": enabled,
        "auto_load_models": bool(row["autoLoadModels"]),
        "model_sync_interval_seconds": 3600,
        "price_multiplier": "1.00",
        "protocols": _provider_protocols(connection, tables, row, enabled),
    }


def _provider_protocols(
    connection: sqlite3.Connection,
    tables: set[str],
    provider: sqlite3.Row,
    enabled: bool,
) -> list[dict[str, object]]:
    provider_type_rows: list[sqlite3.Row] = []
    if "ProviderType" in tables:
        provider_type_rows = connection.execute(
            'SELECT type, "baseURL" FROM "ProviderType" WHERE "providerId" = ?', (provider["id"],)
        ).fetchall()
    if provider_type_rows:
        source = [(str(row["type"]), str(row["baseURL"])) for row in provider_type_rows]
    else:
        source = [
            (protocol, str(provider["baseURL"])) for protocol in _legacy_provider_types(provider)
        ]
    protocols = {(_normalize_protocol(protocol), base_url) for protocol, base_url in source}
    return [
        {
            "protocol": protocol,
            "base_url": base_url,
            "websocket_url": None,
            "extra_headers": None,
            "supports_responses": True,
            "enabled": enabled,
        }
        for protocol, base_url in sorted(protocols)
    ]


def _legacy_provider_types(provider: sqlite3.Row) -> list[str]:
    raw_types = provider["types"]
    if raw_types:
        try:
            types = json.loads(str(raw_types))
        except (TypeError, json.JSONDecodeError) as error:
            raise LegacyExportError(
                f"Invalid JSON in Provider.types for {provider['name']}"
            ) from error
        if not isinstance(types, list) or not all(isinstance(item, str) for item in types):
            raise LegacyExportError(f"Invalid JSON in Provider.types for {provider['name']}")
        if types:
            return types
    if provider["type"]:
        return [str(provider["type"])]
    return ["openai"]


def _normalize_protocol(protocol: str) -> str:
    normalized = protocol.lower()
    return "claude" if normalized == "anthropic" else normalized


def _models(
    connection: sqlite3.Connection,
    tables: set[str],
    model_ids: set[int],
    providers: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    if not model_ids:
        return []
    placeholders = ", ".join("?" for _ in model_ids)
    rows = connection.execute(
        f'SELECT * FROM "Model" WHERE id IN ({placeholders}) ORDER BY name, id',
        tuple(sorted(model_ids)),
    ).fetchall()
    aliases = _model_aliases(connection, tables, rows)
    return [
        {
            "canonical_name": str(row["name"]),
            "display_name": str(row["name"]),
            "input_price_per_million": _legacy_price(row["inputTokenPrice"]),
            "output_price_per_million": _legacy_price(row["outputTokenPrice"]),
            "cache_read_price_per_million": "0",
            "cache_write_price_per_million": "0",
            "price_multiplier": "1.00",
            "enabled": True,
            "routing_strategy": "weighted_random",
            "aliases": aliases.get(int(row["id"]), []),
            "routes": _routes(connection, tables, row, providers),
        }
        for row in rows
    ]


def _legacy_price(value: object) -> str:
    try:
        price = Decimal(str(value or 0)) / Decimal("10")
    except (InvalidOperation, ValueError) as error:
        raise LegacyExportError(f"Invalid legacy token price: {value!r}") from error
    if price < 0:
        raise LegacyExportError(f"Invalid legacy token price: {value!r}")
    return format(price, "f").rstrip("0").rstrip(".") or "0"


def _model_aliases(
    connection: sqlite3.Connection, tables: set[str], models: list[sqlite3.Row]
) -> dict[int, list[dict[str, object]]]:
    aliases: dict[int, set[str]] = {int(model["id"]): set() for model in models}
    if "ModelAlias" in tables:
        model_ids = tuple(aliases)
        placeholders = ", ".join("?" for _ in model_ids)
        for row in connection.execute(
            f'SELECT "modelId", alias FROM "ModelAlias" WHERE "modelId" IN ({placeholders})',
            model_ids,
        ):
            aliases[int(row["modelId"])].add(str(row["alias"]))
    for model in models:
        if model["alias"]:
            aliases[int(model["id"])].add(str(model["alias"]))
    seen: dict[str, int] = {}
    for model_id, model_aliases in aliases.items():
        for alias in model_aliases:
            owner = seen.setdefault(alias, model_id)
            if owner != model_id:
                raise LegacyExportError(f"Alias conflict for {alias}")
    return {
        model_id: [{"alias": alias, "enabled": True} for alias in sorted(model_aliases)]
        for model_id, model_aliases in aliases.items()
    }


def _routes(
    connection: sqlite3.Connection,
    tables: set[str],
    model: sqlite3.Row,
    providers: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    if "ModelRoute" not in tables or not providers:
        return []
    rows = connection.execute(
        """SELECT route.*, provider.name AS provider_name
            FROM "ModelRoute" AS route
            JOIN "Provider" AS provider ON provider.id = route."providerId"
            WHERE route."modelId" = ?
            ORDER BY provider.name, route.id""",
        (model["id"],),
    ).fetchall()
    converted: list[dict[str, object]] = []
    for row in rows:
        provider = providers.get(str(row["provider_name"]))
        if provider is None:
            continue
        weight = int(row["weight"])
        if not 1 <= weight <= 10000:
            raise LegacyExportError(f"Invalid ModelRoute weight: {weight}")
        for protocol in cast(list[dict[str, object]], provider["protocols"]):
            converted.append(
                {
                    "provider": provider["name"],
                    "protocol": protocol["protocol"],
                    "base_url": protocol["base_url"],
                    "upstream_model": str(model["name"]),
                    "weight": weight,
                    "enabled": not bool(row["disabled"]),
                }
            )
    return converted


def _write_bundle(destination: Path, bundle: dict[str, object]) -> None:
    temporary_path: Path | None = None
    file_descriptor: int | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
        temporary_path = Path(temporary_name)
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as output:
            file_descriptor = None
            output.write(json.dumps(bundle, indent=2, sort_keys=True))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export one user's legacy SQLite catalog.")
    parser.add_argument("database", metavar="DATABASE")
    parser.add_argument("--user", required=True, metavar="USER")
    parser.add_argument("--output", required=True, metavar="FILE")
    parser.add_argument("--include-unowned", action="store_true")
    parser.add_argument("--include-secrets", action="store_true")
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args(argv)
    output_path = Path(arguments.output)
    if output_path.exists() and not arguments.force:
        print(
            f"error: output file already exists: {output_path} (use --force to replace it)",
            file=sys.stderr,
        )
        return 1
    try:
        bundle = export_legacy_catalog(
            arguments.database,
            arguments.user,
            arguments.include_unowned,
            arguments.include_secrets,
        )
        _write_bundle(output_path, bundle)
    except (LegacyExportError, OSError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    provider_count = len(cast(list[object], bundle["providers"]))
    model_count = len(cast(list[object], bundle["models"]))
    print(f"Exported {provider_count} provider(s) and {model_count} model(s) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
