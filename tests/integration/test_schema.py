from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from ai_gateway.core.enums import (
    ApiKeyScope,
    LedgerKind,
    Protocol,
    RequestStatus,
    RouteRuntimeState,
    UsageSource,
)
from ai_gateway.db.base import Base
from ai_gateway.db.models import (
    Account,
    ApiKey,
    ApiKeyModel,
    ApiKeyProvider,
    LedgerEntry,
    Model,
    ModelAlias,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    User,
)


def test_schema_contains_exact_tables_and_columns() -> None:
    expected = {
        "users": {
            "id",
            "email",
            "password_hash",
            "role",
            "is_active",
            "totp_secret_encrypted",
            "pending_totp_secret_encrypted",
            "totp_enabled",
            "created_at",
            "updated_at",
        },
        "accounts": {"id", "user_id", "balance", "total_spent", "version"},
        "api_keys": {
            "id",
            "user_id",
            "name",
            "key_prefix",
            "key_hash",
            "scope",
            "is_active",
            "expires_at",
            "last_used_at",
            "created_at",
        },
        "api_key_providers": {"api_key_id", "provider_id"},
        "api_key_models": {"api_key_id", "model_id"},
        "providers": {
            "id",
            "name",
            "credential_encrypted",
            "enabled",
            "auto_load_models",
            "model_sync_interval_seconds",
            "last_model_sync_at",
        },
        "provider_protocols": {
            "id",
            "provider_id",
            "protocol",
            "base_url",
            "websocket_url",
            "extra_headers_encrypted",
            "enabled",
        },
        "models": {
            "id",
            "canonical_name",
            "display_name",
            "enabled",
            "input_price_per_million",
            "output_price_per_million",
            "routing_strategy",
            "created_at",
            "updated_at",
        },
        "model_aliases": {"id", "model_id", "alias", "enabled"},
        "model_routes": {
            "id",
            "model_id",
            "provider_id",
            "provider_protocol_id",
            "upstream_model",
            "weight",
            "enabled",
            "source",
            "runtime_state",
            "consecutive_failures",
            "disabled_until",
            "last_error_code",
            "last_error_at",
        },
        "ledger_entries": {
            "id",
            "account_id",
            "request_id",
            "idempotency_key",
            "kind",
            "amount",
            "balance_after",
            "metadata",
            "created_at",
        },
        "request_logs": {
            "id",
            "user_id",
            "api_key_id",
            "model_id",
            "provider_id",
            "model_route_id",
            "inbound_protocol",
            "outbound_protocol",
            "transport",
            "stream",
            "status",
            "http_status",
            "prompt_tokens",
            "completion_tokens",
            "usage_source",
            "cost",
            "latency_ms",
            "first_token_ms",
            "error_code",
            "request_detail_gzip",
            "response_detail_gzip",
            "created_at",
            "completed_at",
        },
    }

    assert set(Base.metadata.tables) == set(expected)
    for table_name, column_names in expected.items():
        assert set(Base.metadata.tables[table_name].columns.keys()) == column_names


def test_schema_exposes_required_enums() -> None:
    assert {item.value for item in Protocol} == {"openai", "claude", "gemini"}
    assert {item.value for item in ApiKeyScope} == {
        "all",
        "providers",
        "models",
        "providers_and_models",
    }
    assert {item.value for item in RouteRuntimeState} == {"closed", "open", "half_open"}
    assert {item.value for item in LedgerKind} >= {
        "reservation",
        "reservation_release",
        "usage",
        "adjustment",
    }
    assert {item.value for item in RequestStatus} == {
        "started",
        "completed",
        "failed",
        "client_disconnected",
    }
    assert {item.value for item in UsageSource} == {"provider", "estimated"}


def test_required_unique_constraints_and_indexes_are_declared() -> None:
    def unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
        table = Base.metadata.tables[table_name]
        return {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }

    assert ("email",) in unique_column_sets("users")
    assert ("user_id",) in unique_column_sets("accounts")
    assert ("key_hash",) in unique_column_sets("api_keys")
    assert ("name",) in unique_column_sets("providers")
    assert ("provider_id", "protocol", "base_url") in unique_column_sets("provider_protocols")
    assert ("canonical_name",) in unique_column_sets("models")
    assert ("alias",) in unique_column_sets("model_aliases")
    assert ("model_id", "provider_id", "provider_protocol_id") in unique_column_sets("model_routes")
    assert ("idempotency_key",) in unique_column_sets("ledger_entries")

    route_indexes = {
        tuple(column.name for column in index.columns)
        for index in Base.metadata.tables["model_routes"].indexes
    }
    assert ("model_id", "enabled", "runtime_state") in route_indexes

    api_key_indexes = {
        tuple(column.name for column in index.columns)
        for index in Base.metadata.tables["api_keys"].indexes
    }
    assert ("key_prefix",) in api_key_indexes

    request_log_indexes = {
        tuple(column.name for column in index.columns)
        for index in Base.metadata.tables["request_logs"].indexes
    }
    assert request_log_indexes >= {
        ("user_id", "created_at"),
        ("api_key_id", "created_at"),
        ("provider_id", "created_at"),
        ("status", "created_at"),
    }

    assert {column.name for column in inspect(ApiKeyProvider).primary_key} == {
        "api_key_id",
        "provider_id",
    }
    assert {column.name for column in inspect(ApiKeyModel).primary_key} == {
        "api_key_id",
        "model_id",
    }


async def test_model_route_is_unique_per_model_provider_protocol(session) -> None:
    model = Model(
        canonical_name="gateway-model",
        display_name="Gateway Model",
        input_price_per_million=Decimal("0"),
        output_price_per_million=Decimal("0"),
    )
    provider = Provider(name="vendor", credential_encrypted=b"secret")
    protocol = ProviderProtocol(
        provider=provider,
        protocol=Protocol.OPENAI,
        base_url="https://api.example.com/v1",
    )
    session.add_all([model, provider, protocol])
    await session.flush()

    session.add_all(
        [
            ModelRoute(
                model_id=model.id,
                provider_id=provider.id,
                provider_protocol_id=protocol.id,
                upstream_model="gpt-4.1-mini",
                weight=100,
            ),
            ModelRoute(
                model_id=model.id,
                provider_id=provider.id,
                provider_protocol_id=protocol.id,
                upstream_model="gpt-4.1-mini-duplicate",
                weight=100,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_money_columns_are_decimal(session) -> None:
    user = User(email="a@example.com", password_hash="x", role="user")
    user.account = Account(balance=Decimal("10.00000000"), total_spent=Decimal("0"))
    session.add(user)

    await session.commit()

    assert isinstance(user.account.balance, Decimal)
    assert user.account.balance == Decimal("10.00000000")
    assert isinstance(user.account.total_spent, Decimal)


# Keep imports above explicit: these assertions ensure all public ORM classes remain exported.
assert all(
    model is not None
    for model in (
        User,
        ApiKey,
        ApiKeyProvider,
        ApiKeyModel,
        Provider,
        ProviderProtocol,
        Model,
        ModelAlias,
        ModelRoute,
        Account,
        LedgerEntry,
        RequestLog,
    )
)
