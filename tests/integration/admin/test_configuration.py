from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.core.enums import Protocol, RouteRuntimeState, RouteSource
from ai_gateway.core.security import decrypt_secret, encrypt_secret
from ai_gateway.db.models import Model, ModelAlias, ModelRoute, Provider, ProviderProtocol


async def test_admin_exports_deterministic_redacted_catalog_bundle(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    provider_a = Provider(
        name="provider-a",
        credential_encrypted=encrypt_secret(
            '{"api_key":"upstream-secret"}', settings=admin_settings
        ),
        enabled=False,
        auto_load_models=True,
        model_sync_interval_seconds=17,
        price_multiplier=Decimal("1.25"),
    )
    provider_a.protocols = [
        ProviderProtocol(
            protocol=Protocol.OPENAI,
            base_url="https://provider-a.example/v1",
            websocket_url="wss://provider-a.example/v1",
            extra_headers_encrypted=encrypt_secret(
                '{"X-Tenant":"secret-tenant"}', settings=admin_settings
            ),
            supports_responses=False,
            enabled=False,
        )
    ]
    provider_z = Provider(
        name="provider-z",
        credential_encrypted=encrypt_secret("{}", settings=admin_settings),
    )
    provider_z.protocols = [
        ProviderProtocol(
            protocol=Protocol.CLAUDE,
            base_url="https://provider-z.example",
        )
    ]
    model_a = Model(
        canonical_name="model-a",
        display_name="Model A",
        input_price_per_million=Decimal("0.12345678"),
        output_price_per_million=Decimal("1.23456789"),
        cache_read_price_per_million=Decimal("0.01234567"),
        cache_write_price_per_million=Decimal("0.12345678"),
        price_multiplier=Decimal("1.50"),
        enabled=False,
        routing_strategy="weighted_random",
        aliases=[
            ModelAlias(alias="model-a-enabled", enabled=True),
            ModelAlias(alias="model-a-disabled", enabled=False),
        ],
    )
    model_z = Model(canonical_name="model-z", display_name="Model Z")
    session.add_all([provider_z, provider_a, model_z, model_a])
    await session.flush()
    session.add(
        ModelRoute(
            model_id=model_a.id,
            provider_id=provider_a.id,
            provider_protocol_id=provider_a.protocols[0].id,
            upstream_model="upstream-model-a",
            weight=321,
            enabled=False,
        )
    )
    await session.flush()

    response = await admin_client.get("/admin/configuration/export")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == (
        'attachment; filename="ai-gateway-catalog-v1.json"'
    )
    assert response.json() == {
        "format": "ai-gateway.catalog",
        "version": 1,
        "providers": [
            {
                "name": "provider-a",
                "credential": None,
                "enabled": False,
                "auto_load_models": True,
                "model_sync_interval_seconds": 17,
                "price_multiplier": 1.25,
                "protocols": [
                    {
                        "protocol": "openai",
                        "base_url": "https://provider-a.example/v1",
                        "websocket_url": "wss://provider-a.example/v1",
                        "extra_headers": None,
                        "supports_responses": False,
                        "enabled": False,
                    }
                ],
            },
            {
                "name": "provider-z",
                "credential": None,
                "enabled": True,
                "auto_load_models": False,
                "model_sync_interval_seconds": 3600,
                "price_multiplier": 1.0,
                "protocols": [
                    {
                        "protocol": "claude",
                        "base_url": "https://provider-z.example",
                        "websocket_url": None,
                        "extra_headers": None,
                        "supports_responses": True,
                        "enabled": True,
                    }
                ],
            },
        ],
        "models": [
            {
                "canonical_name": "model-a",
                "display_name": "Model A",
                "input_price_per_million": 0.12345678,
                "output_price_per_million": 1.23456789,
                "cache_read_price_per_million": 0.01234567,
                "cache_write_price_per_million": 0.12345678,
                "price_multiplier": 1.5,
                "enabled": False,
                "routing_strategy": "weighted_random",
                "aliases": [
                    {"alias": "model-a-disabled", "enabled": False},
                    {"alias": "model-a-enabled", "enabled": True},
                ],
                "routes": [
                    {
                        "provider": "provider-a",
                        "protocol": "openai",
                        "base_url": "https://provider-a.example/v1",
                        "upstream_model": "upstream-model-a",
                        "weight": 321,
                        "enabled": False,
                    }
                ],
            },
            {
                "canonical_name": "model-z",
                "display_name": "Model Z",
                "input_price_per_million": 0.0,
                "output_price_per_million": 0.0,
                "cache_read_price_per_million": 0.0,
                "cache_write_price_per_million": 0.0,
                "price_multiplier": 1.0,
                "enabled": True,
                "routing_strategy": "weighted_random",
                "aliases": [],
                "routes": [],
            },
        ],
    }
    assert b"upstream-secret" not in response.content
    assert b"secret-tenant" not in response.content


async def test_admin_exports_catalog_secrets_only_when_explicitly_requested(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    provider = Provider(
        name="secret-provider",
        credential_encrypted=encrypt_secret(
            '{"api_key":"literal-upstream-secret"}', settings=admin_settings
        ),
    )
    provider.protocols = [
        ProviderProtocol(
            protocol=Protocol.OPENAI,
            base_url="https://secret-provider.example/v1",
            extra_headers_encrypted=encrypt_secret(
                '{"X-Literal-Tenant":"literal-header-secret"}', settings=admin_settings
            ),
        )
    ]
    session.add(provider)
    await session.flush()

    response = await admin_client.get("/admin/configuration/export?include_secrets=true")

    assert response.status_code == 200, response.text
    assert response.json()["providers"] == [
        {
            "name": "secret-provider",
            "credential": {"api_key": "literal-upstream-secret"},
            "enabled": True,
            "auto_load_models": False,
            "model_sync_interval_seconds": 3600,
            "price_multiplier": 1.0,
            "protocols": [
                {
                    "protocol": "openai",
                    "base_url": "https://secret-provider.example/v1",
                    "websocket_url": None,
                    "extra_headers": {"X-Literal-Tenant": "literal-header-secret"},
                    "supports_responses": True,
                    "enabled": True,
                }
            ],
        }
    ]


async def test_catalog_configuration_requires_admin(
    non_admin_client: AsyncClient,
) -> None:
    export_response = await non_admin_client.get("/admin/configuration/export")
    import_response = await non_admin_client.post(
        "/admin/configuration/import",
        json={"format": "ai-gateway.catalog", "version": 1, "providers": [], "models": []},
    )

    assert export_response.status_code == import_response.status_code == 403
    assert export_response.json()["detail"]["code"] == "admin_required"
    assert import_response.json()["detail"]["code"] == "admin_required"


def _import_bundle(
    *,
    credential: dict[str, object] | None = None,
    extra_headers: dict[str, object] | None = None,
    provider_enabled: bool = True,
    model_enabled: bool = True,
    provider_multiplier: float = 1.25,
    input_price: float = 0.11,
    output_price: float = 0.22,
    cache_read_price: float = 0.03,
    cache_write_price: float = 0.04,
    model_multiplier: float = 1.5,
    route_upstream_model: str = "imported-upstream-model",
    route_weight: int = 100,
) -> dict[str, object]:
    return {
        "format": "ai-gateway.catalog",
        "version": 1,
        "providers": [
            {
                "name": "import-provider",
                "credential": credential,
                "enabled": provider_enabled,
                "auto_load_models": True,
                "model_sync_interval_seconds": 91,
                "price_multiplier": provider_multiplier,
                "protocols": [
                    {
                        "protocol": "openai",
                        "base_url": "https://import-provider.example/v1",
                        "websocket_url": "wss://import-provider.example/v1",
                        "extra_headers": extra_headers,
                        "supports_responses": False,
                        "enabled": provider_enabled,
                    }
                ],
            }
        ],
        "models": [
            {
                "canonical_name": "import-model",
                "display_name": "Imported Model",
                "input_price_per_million": input_price,
                "output_price_per_million": output_price,
                "cache_read_price_per_million": cache_read_price,
                "cache_write_price_per_million": cache_write_price,
                "price_multiplier": model_multiplier,
                "enabled": model_enabled,
                "routing_strategy": "weighted_random",
                "aliases": [
                    {"alias": "import-enabled", "enabled": True},
                    {"alias": "import-disabled", "enabled": False},
                ],
                "routes": [
                    {
                        "provider": "import-provider",
                        "protocol": "openai",
                        "base_url": "https://import-provider.example/v1",
                        "upstream_model": route_upstream_model,
                        "weight": route_weight,
                        "enabled": model_enabled,
                    }
                ],
            }
        ],
    }


async def test_admin_import_creates_catalog_resources_and_redacted_secrets_use_empty_values(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    response = await admin_client.post("/admin/configuration/import", json=_import_bundle())

    assert response.status_code == 200, response.text
    assert response.json() == {
        "providers_created": 1,
        "providers_updated": 0,
        "models_created": 1,
        "models_updated": 0,
        "routes_created": 1,
        "routes_updated": 0,
    }
    provider = await session.scalar(
        select(Provider)
        .where(Provider.name == "import-provider")
        .options(selectinload(Provider.protocols))
    )
    model = await session.scalar(
        select(Model)
        .where(Model.canonical_name == "import-model")
        .options(selectinload(Model.aliases), selectinload(Model.routes))
    )
    assert provider is not None
    assert decrypt_secret(provider.credential_encrypted, settings=admin_settings) == "{}"
    assert provider.enabled is True
    assert provider.auto_load_models is True
    assert provider.model_sync_interval_seconds == 91
    assert provider.price_multiplier == Decimal("1.25")
    assert len(provider.protocols) == 1
    assert provider.protocols[0].extra_headers_encrypted is None
    assert model is not None
    assert model.input_price_per_million == Decimal("0.11000000")
    assert model.output_price_per_million == Decimal("0.22000000")
    assert model.cache_read_price_per_million == Decimal("0.03000000")
    assert model.cache_write_price_per_million == Decimal("0.04000000")
    assert model.price_multiplier == Decimal("1.50")
    assert {(alias.alias, alias.enabled) for alias in model.aliases} == {
        ("import-enabled", True),
        ("import-disabled", False),
    }
    assert len(model.routes) == 1
    route = model.routes[0]
    assert route.source is RouteSource.MANUAL
    assert route.runtime_state is RouteRuntimeState.CLOSED
    assert route.consecutive_failures == 0
    assert route.disabled_until is None
    assert route.last_error_code is None
    assert route.last_error_at is None


async def test_admin_import_merges_without_duplicates_and_preserves_redacted_existing_secrets(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    created = await admin_client.post(
        "/admin/configuration/import",
        json=_import_bundle(
            credential={"api_key": "preserved-credential"},
            extra_headers={"X-Imported": "preserved-header"},
        ),
    )
    assert created.status_code == 200, created.text
    provider = await session.scalar(
        select(Provider)
        .where(Provider.name == "import-provider")
        .options(selectinload(Provider.protocols))
    )
    model = await session.scalar(
        select(Model)
        .where(Model.canonical_name == "import-model")
        .options(selectinload(Model.routes))
    )
    assert provider is not None
    assert model is not None
    protocol = provider.protocols[0]
    route = model.routes[0]
    credential_before = provider.credential_encrypted
    headers_before = protocol.extra_headers_encrypted
    route.runtime_state = RouteRuntimeState.OPEN
    route.consecutive_failures = 7
    route.last_error_code = "upstream_failure"
    await session.flush()
    session.add(
        Provider(
            name="untouched-provider",
            credential_encrypted=credential_before,
            enabled=False,
        )
    )
    session.add(Model(canonical_name="untouched-model", display_name="Untouched", enabled=False))
    await session.flush()

    updated = await admin_client.post(
        "/admin/configuration/import",
        json=_import_bundle(
            credential=None,
            extra_headers=None,
            provider_enabled=False,
            model_enabled=False,
            provider_multiplier=2.25,
            input_price=1.11,
            output_price=2.22,
            cache_read_price=0.13,
            cache_write_price=0.14,
            model_multiplier=2.5,
            route_upstream_model="updated-upstream-model",
            route_weight=777,
        ),
    )

    assert updated.status_code == 200, updated.text
    assert updated.json() == {
        "providers_created": 0,
        "providers_updated": 1,
        "models_created": 0,
        "models_updated": 1,
        "routes_created": 0,
        "routes_updated": 1,
    }
    await session.refresh(provider)
    await session.refresh(protocol)
    await session.refresh(model, attribute_names=["aliases", "routes"])
    await session.refresh(route)
    assert provider.credential_encrypted == credential_before
    assert protocol.extra_headers_encrypted == headers_before
    assert decrypt_secret(provider.credential_encrypted, settings=admin_settings) == (
        '{"api_key":"preserved-credential"}'
    )
    assert decrypt_secret(protocol.extra_headers_encrypted, settings=admin_settings) == (
        '{"X-Imported":"preserved-header"}'
    )
    assert provider.enabled is False
    assert protocol.enabled is False
    assert model.enabled is False
    assert provider.price_multiplier == Decimal("2.25")
    assert model.input_price_per_million == Decimal("1.11000000")
    assert model.output_price_per_million == Decimal("2.22000000")
    assert model.cache_read_price_per_million == Decimal("0.13000000")
    assert model.cache_write_price_per_million == Decimal("0.14000000")
    assert model.price_multiplier == Decimal("2.50")
    assert len(model.aliases) == 2
    assert len(model.routes) == 1
    assert route.upstream_model == "updated-upstream-model"
    assert route.weight == 777
    assert route.enabled is False
    assert route.runtime_state is RouteRuntimeState.OPEN
    assert route.consecutive_failures == 7
    assert route.last_error_code == "upstream_failure"
    untouched_provider = await session.scalar(
        select(Provider).where(Provider.name == "untouched-provider")
    )
    untouched_model = await session.scalar(
        select(Model).where(Model.canonical_name == "untouched-model")
    )
    assert untouched_provider is not None and untouched_provider.enabled is False
    assert untouched_model is not None and untouched_model.enabled is False


async def test_admin_import_conflict_rolls_back_all_bundle_changes(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    session.add(
        Model(
            canonical_name="existing-model",
            display_name="Existing Model",
            aliases=[ModelAlias(alias="globally-taken-alias")],
        )
    )
    await session.flush()
    bundle = _import_bundle(credential={"api_key": "must-not-persist"})
    bundle["models"] = [
        {
            "canonical_name": "new-conflicting-model",
            "display_name": "New Conflicting Model",
            "aliases": [{"alias": "globally-taken-alias", "enabled": True}],
            "routes": [],
        }
    ]

    response = await admin_client.post("/admin/configuration/import", json=bundle)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "catalog_import_conflict"
    assert await session.scalar(select(Provider).where(Provider.name == "import-provider")) is None
    assert (
        await session.scalar(select(Model).where(Model.canonical_name == "new-conflicting-model"))
        is None
    )
    existing = await session.scalar(select(Model).where(Model.canonical_name == "existing-model"))
    assert existing is not None


async def test_admin_import_rejects_invalid_bundle_and_dangling_route_references(
    admin_client: AsyncClient,
) -> None:
    invalid_format = await admin_client.post(
        "/admin/configuration/import",
        json={"format": "wrong-format", "version": 1, "providers": [], "models": []},
    )
    invalid_version = await admin_client.post(
        "/admin/configuration/import",
        json={"format": "ai-gateway.catalog", "version": 2, "providers": [], "models": []},
    )
    dangling_route = await admin_client.post(
        "/admin/configuration/import",
        json={
            "format": "ai-gateway.catalog",
            "version": 1,
            "providers": [],
            "models": [
                {
                    "canonical_name": "dangling-model",
                    "display_name": "Dangling Model",
                    "routes": [
                        {
                            "provider": "missing-provider",
                            "protocol": "openai",
                            "base_url": "https://missing.example/v1",
                            "upstream_model": "missing-upstream-model",
                            "weight": 1,
                            "enabled": True,
                        }
                    ],
                }
            ],
        },
    )

    assert invalid_format.status_code == 422
    assert invalid_version.status_code == 422
    assert dangling_route.status_code == 422


async def test_admin_import_rejects_alias_that_collides_with_existing_canonical_name(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    session.add(Model(canonical_name="canonical-alias-collision", display_name="Existing"))
    await session.flush()
    bundle = _import_bundle()
    bundle["models"] = [
        {
            "canonical_name": "new-collision-model",
            "display_name": "New Collision Model",
            "aliases": [{"alias": "canonical-alias-collision", "enabled": True}],
            "routes": [],
        }
    ]

    response = await admin_client.post("/admin/configuration/import", json=bundle)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "catalog_import_conflict"
    assert await session.scalar(select(Provider).where(Provider.name == "import-provider")) is None
    assert (
        await session.scalar(select(Model).where(Model.canonical_name == "new-collision-model"))
        is None
    )


async def test_catalog_export_and_import_preserve_max_precision_prices(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    exact_price = Decimal("999999999999.12345678")
    model = Model(
        canonical_name="max-precision-model",
        display_name="Max Precision Model",
        input_price_per_million=exact_price,
        output_price_per_million=exact_price,
        cache_read_price_per_million=exact_price,
        cache_write_price_per_million=exact_price,
    )
    session.add(model)
    await session.flush()

    exported = await admin_client.get("/admin/configuration/export")

    assert exported.status_code == 200, exported.text
    assert b"999999999999.12345678" in exported.content
    imported = await admin_client.post(
        "/admin/configuration/import",
        content=exported.content,
        headers={"Content-Type": "application/json"},
    )
    assert imported.status_code == 200, imported.text
    await session.refresh(model)
    assert model.input_price_per_million == exact_price
    assert model.output_price_per_million == exact_price
    assert model.cache_read_price_per_million == exact_price
    assert model.cache_write_price_per_million == exact_price


async def test_admin_import_requires_explicit_format_and_version(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/admin/configuration/import",
        json={"providers": [], "models": []},
    )

    assert response.status_code == 422


async def test_admin_import_rejects_duplicate_aliases_for_one_model(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/admin/configuration/import",
        json={
            "format": "ai-gateway.catalog",
            "version": 1,
            "providers": [],
            "models": [
                {
                    "canonical_name": "duplicate-alias-model",
                    "display_name": "Duplicate Alias Model",
                    "aliases": [
                        {"alias": "same-alias", "enabled": True},
                        {"alias": "same-alias", "enabled": False},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "catalog_import_invalid"
