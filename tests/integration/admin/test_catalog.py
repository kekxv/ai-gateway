from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.catalog.repository import CatalogRepository
from ai_gateway.core.enums import Protocol
from ai_gateway.core.security import decrypt_secret
from ai_gateway.db.models import ModelRoute, Provider, RequestLog, User


async def _create_provider(
    admin_client: AsyncClient,
    *,
    name: str = "vendor-a",
    protocols: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    response = await admin_client.post(
        "/admin/providers",
        json={
            "name": name,
            "credential": {"z_key": "last", "api_key": "secret"},
            "enabled": True,
            "auto_load_models": True,
            "protocols": protocols
            or [
                {
                    "protocol": "openai",
                    "base_url": "https://api.example.com/v1",
                    "extra_headers": {"z-header": "last", "a-header": "first"},
                    "supports_responses": False,
                    "enabled": True,
                },
                {
                    "protocol": "claude",
                    "base_url": "https://api.example.com",
                    "enabled": True,
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_model(
    admin_client: AsyncClient,
    *,
    canonical_name: str = "gpt-4.1-mini",
    aliases: list[str] | None = None,
) -> dict[str, object]:
    response = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": canonical_name,
            "display_name": "Fast Chat",
            "input_price_per_million": "0.15000000",
            "output_price_per_million": "0.60000000",
            "enabled": True,
            "aliases": aliases if aliases is not None else ["fast-chat"],
            "routing_strategy": "weighted_random",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_provider_crud_supports_multiple_protocols_and_hides_secrets(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    body = await _create_provider(admin_client)

    assert body["name"] == "vendor-a"
    assert body["has_credential"] is True
    assert len(body["protocols"]) == 2
    assert body["protocols"][0]["has_extra_headers"] is True
    assert body["protocols"][0]["supports_responses"] is False
    assert body["protocols"][1]["supports_responses"] is True
    serialized = str(body).lower()
    assert "secret" not in serialized
    assert "credential_encrypted" not in serialized
    assert "extra_headers_encrypted" not in serialized

    provider = await session.get(Provider, body["id"])
    assert provider is not None
    assert decrypt_secret(provider.credential_encrypted, settings=admin_settings) == (
        '{"api_key":"secret","z_key":"last"}'
    )
    assert (
        decrypt_secret(
            provider.protocols[0].extra_headers_encrypted,
            settings=admin_settings,
        )
        == '{"a-header":"first","z-header":"last"}'
    )


async def test_provider_create_without_credential_persists_empty_encrypted_object(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    response = await admin_client.post(
        "/admin/providers",
        json={"name": f"ollama-{uuid4().hex}", "protocols": []},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["has_credential"] is False
    assert "credential" not in body
    assert "credential_encrypted" not in body

    provider = await session.get(Provider, body["id"])
    assert provider is not None
    assert decrypt_secret(provider.credential_encrypted, settings=admin_settings) == "{}"

    listing = await admin_client.get("/admin/providers")
    detail = await admin_client.get(f"/admin/providers/{body['id']}")

    assert listing.status_code == detail.status_code == 200
    listed = next(item for item in listing.json() if item["id"] == body["id"])
    assert listed["has_credential"] is False
    assert detail.json() == body


@pytest.mark.parametrize(
    "credential",
    [
        {"api_key": "secret", "auth_scheme": "Basic"},
        {
            "api_key": "secret",
            "auth_scheme": "Bearer",
            "auth_header": "X-Provider-Key\r\nInjected",
        },
        {"api_key": "secret", "auth_scheme": "ApiKey", "auth_header": "Host"},
    ],
)
async def test_provider_rejects_unsafe_guided_auth_configuration(
    credential: dict[str, object],
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/admin/providers",
        json={"name": f"unsafe-auth-{uuid4().hex}", "credential": credential},
    )

    assert response.status_code == 422
    assert "secret" not in response.text


async def test_provider_uses_runtime_model_sync_interval_default(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    admin_settings.model_sync_interval_seconds = 73

    body = await _create_provider(admin_client, name=f"runtime-sync-{uuid4().hex}")

    assert body["model_sync_interval_seconds"] == 73
    provider = await session.get(Provider, body["id"])
    assert provider is not None
    assert provider.model_sync_interval_seconds == 73

    listing = await admin_client.get("/admin/providers")
    detail = await admin_client.get(f"/admin/providers/{body['id']}")
    updated = await admin_client.patch(
        f"/admin/providers/{body['id']}",
        json={"enabled": False, "credential": {"replacement": "new-secret"}},
    )

    assert listing.status_code == detail.status_code == updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert "new-secret" not in updated.text
    await session.refresh(provider)
    assert decrypt_secret(provider.credential_encrypted, settings=admin_settings) == (
        '{"replacement":"new-secret"}'
    )


async def test_duplicate_provider_protocol_tuple_is_rejected(
    admin_client: AsyncClient,
) -> None:
    duplicate = {
        "protocol": "openai",
        "base_url": "https://api.example.com/v1",
        "enabled": True,
    }

    response = await admin_client.post(
        "/admin/providers",
        json={
            "name": "duplicate-protocols",
            "credential": {"api_key": "secret"},
            "protocols": [duplicate, duplicate],
        },
    )

    assert response.status_code == 422
    assert "secret" not in response.text


@pytest.mark.parametrize(
    ("payload", "secret_marker"),
    [
        (
            {
                "name": "invalid-credential",
                "credential": "credential-secret-7f67a",
                "protocols": [],
            },
            b"credential-secret-7f67a",
        ),
        (
            {
                "name": "invalid-extra-headers",
                "credential": {},
                "protocols": [
                    {
                        "protocol": "openai",
                        "base_url": "https://api.example.com/v1",
                        "extra_headers": "header-secret-8b12c",
                    }
                ],
            },
            b"header-secret-8b12c",
        ),
    ],
)
async def test_validation_errors_never_echo_secret_inputs(
    payload: dict[str, object],
    secret_marker: bytes,
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post("/admin/providers", json=payload)

    assert response.status_code == 422
    assert secret_marker not in response.content
    assert all(set(error) == {"loc", "msg", "type"} for error in response.json()["detail"])


async def test_protocol_header_update_omission_preserves_and_null_clears(
    admin_client: AsyncClient,
    admin_settings,
    session: AsyncSession,
) -> None:
    body = await _create_provider(
        admin_client,
        protocols=[
            {
                "protocol": "openai",
                "base_url": "https://api.example.com/v1",
                "extra_headers": {"Authorization": "header-secret"},
                "enabled": True,
            }
        ],
    )
    provider = await session.get(Provider, body["id"])
    assert provider is not None
    protocol = provider.protocols[0]
    credential_before = provider.credential_encrypted
    headers_before = protocol.extra_headers_encrypted
    assert headers_before is not None

    omitted = await admin_client.patch(
        f"/admin/providers/{body['id']}",
        json={
            "enabled": False,
            "protocols": [
                {
                    "id": body["protocols"][0]["id"],
                    "protocol": "openai",
                    "base_url": "https://api.example.com/v1",
                    "enabled": False,
                }
            ],
        },
    )
    await session.refresh(provider)
    await session.refresh(protocol)

    assert omitted.status_code == 200, omitted.text
    assert omitted.json()["protocols"][0]["has_extra_headers"] is True
    assert provider.credential_encrypted == credential_before
    assert protocol.extra_headers_encrypted == headers_before
    assert (
        decrypt_secret(protocol.extra_headers_encrypted, settings=admin_settings)
        == '{"Authorization":"header-secret"}'
    )

    cleared = await admin_client.patch(
        f"/admin/providers/{body['id']}",
        json={
            "protocols": [
                {
                    "id": body["protocols"][0]["id"],
                    "protocol": "openai",
                    "base_url": "https://api.example.com/v1",
                    "extra_headers": None,
                    "enabled": False,
                }
            ]
        },
    )
    await session.refresh(protocol)

    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["protocols"][0]["has_extra_headers"] is False
    assert protocol.extra_headers_encrypted is None

    null_credential = await admin_client.patch(
        f"/admin/providers/{body['id']}",
        json={"credential": None},
    )
    await session.refresh(provider)

    assert null_credential.status_code == 422
    assert provider.credential_encrypted == credential_before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_price_per_million", "-0.00000001"),
        ("input_price_per_million", "0.000000001"),
        ("output_price_per_million", "-1"),
        ("output_price_per_million", "1.123456789"),
    ],
)
async def test_model_prices_are_non_negative_with_at_most_eight_decimal_places(
    field: str,
    value: str,
    admin_client: AsyncClient,
) -> None:
    payload = {
        "canonical_name": f"invalid-{field}-{value}",
        "display_name": "Invalid Price",
        "input_price_per_million": "0",
        "output_price_per_million": "0",
        "aliases": [],
    }
    payload[field] = value

    response = await admin_client.post("/admin/models", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("weight", [0, 10001])
async def test_route_weight_must_be_in_supported_range(
    weight: int,
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/admin/model-routes",
        json={
            "model_id": 1,
            "provider_id": 1,
            "provider_protocol_id": 1,
            "upstream_model": "provider-native-model",
            "weight": weight,
        },
    )

    assert response.status_code == 422


async def test_route_protocol_must_belong_to_provider(
    admin_client: AsyncClient,
) -> None:
    first = await _create_provider(admin_client, name="first-provider")
    second = await _create_provider(admin_client, name="second-provider")
    model = await _create_model(admin_client)

    response = await admin_client.post(
        "/admin/model-routes",
        json={
            "model_id": model["id"],
            "provider_id": first["id"],
            "provider_protocol_id": second["protocols"][0]["id"],
            "upstream_model": "provider-native-model",
            "weight": 100,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "provider_protocol_mismatch"


async def test_provider_native_upstream_model_may_equal_an_alias(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    provider = await _create_provider(admin_client)
    model = await _create_model(admin_client)
    route_payload = {
        "model_id": model["id"],
        "provider_id": provider["id"],
        "provider_protocol_id": provider["protocols"][0]["id"],
        "weight": 100,
        "enabled": True,
    }

    created = await admin_client.post(
        "/admin/model-routes",
        json={**route_payload, "upstream_model": "fast-chat"},
    )

    assert created.status_code == 201, created.text
    stored = await session.get(ModelRoute, created.json()["id"])
    assert stored is not None
    assert stored.upstream_model == "fast-chat"
    resolved = await CatalogRepository(session).resolve_model("fast-chat")
    assert resolved.model_id == model["id"]
    assert resolved.requested_name == "fast-chat"
    assert resolved.canonical_name == "gpt-4.1-mini"


async def test_alias_may_be_added_after_matching_upstream_route_exists(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    provider = await _create_provider(admin_client)
    model = await _create_model(admin_client, aliases=[])
    created = await admin_client.post(
        "/admin/model-routes",
        json={
            "model_id": model["id"],
            "provider_id": provider["id"],
            "provider_protocol_id": provider["protocols"][0]["id"],
            "upstream_model": "shared-native-name",
        },
    )
    assert created.status_code == 201, created.text

    updated = await admin_client.patch(
        f"/admin/models/{model['id']}",
        json={"aliases": ["shared-native-name"]},
    )

    assert updated.status_code == 200, updated.text
    stored = await session.get(ModelRoute, created.json()["id"])
    assert stored is not None
    assert stored.upstream_model == "shared-native-name"
    resolved = await CatalogRepository(session).resolve_model("shared-native-name")
    assert resolved.model_id == model["id"]


async def test_model_alias_and_route_relations_can_be_updated(
    admin_client: AsyncClient,
) -> None:
    provider = await _create_provider(admin_client)
    model = await _create_model(admin_client)
    route = await admin_client.post(
        "/admin/model-routes",
        json={
            "model_id": model["id"],
            "provider_id": provider["id"],
            "provider_protocol_id": provider["protocols"][0]["id"],
            "upstream_model": "native-original",
            "weight": 100,
        },
    )
    assert route.status_code == 201, route.text

    updated_model = await admin_client.patch(
        f"/admin/models/{model['id']}",
        json={"aliases": [{"alias": "quick-chat", "enabled": False}]},
    )
    updated_route = await admin_client.patch(
        f"/admin/model-routes/{route.json()['id']}",
        json={"upstream_model": "native-revision", "weight": 999, "enabled": False},
    )

    assert updated_model.status_code == updated_route.status_code == 200
    assert updated_model.json()["aliases"] == [
        {"id": updated_model.json()["aliases"][0]["id"], "alias": "quick-chat", "enabled": False}
    ]
    assert updated_route.json()["upstream_model"] == "native-revision"
    assert updated_route.json()["weight"] == 999
    assert updated_route.json()["enabled"] is False


async def test_models_and_routes_have_list_and_detail_crud_views(
    admin_client: AsyncClient,
) -> None:
    provider = await _create_provider(admin_client)
    model = await _create_model(admin_client)
    route = await admin_client.post(
        "/admin/model-routes",
        json={
            "model_id": model["id"],
            "provider_id": provider["id"],
            "provider_protocol_id": provider["protocols"][0]["id"],
            "upstream_model": "native-list-detail",
        },
    )
    assert route.status_code == 201, route.text
    route_body = route.json()

    model_listing = await admin_client.get("/admin/models")
    model_detail = await admin_client.get(f"/admin/models/{model['id']}")
    route_listing = await admin_client.get(
        "/admin/model-routes",
        params={"model_id": model["id"], "provider_id": provider["id"]},
    )
    route_detail = await admin_client.get(f"/admin/model-routes/{route_body['id']}")

    assert model_listing.status_code == model_detail.status_code == 200
    assert model["id"] in {item["id"] for item in model_listing.json()}
    assert model_detail.json() == model
    assert route_listing.status_code == route_detail.status_code == 200
    assert route_listing.json() == [route_body]
    assert route_detail.json() == route_body


async def test_provider_and_model_deletion_with_request_history_returns_conflict(
    admin_client: AsyncClient,
    admin_user_record: User,
    session: AsyncSession,
) -> None:
    provider = await _create_provider(admin_client)
    model = await _create_model(admin_client)
    route = await admin_client.post(
        "/admin/model-routes",
        json={
            "model_id": model["id"],
            "provider_id": provider["id"],
            "provider_protocol_id": provider["protocols"][0]["id"],
            "upstream_model": "native-original",
            "weight": 100,
        },
    )
    assert route.status_code == 201, route.text
    session.add(
        RequestLog(
            id=str(uuid4()),
            user_id=admin_user_record.id,
            model_id=int(model["id"]),
            provider_id=int(provider["id"]),
            model_route_id=route.json()["id"],
            inbound_protocol=Protocol.OPENAI,
            outbound_protocol=Protocol.OPENAI,
            transport="http",
        )
    )
    await session.flush()

    provider_delete = await admin_client.delete(f"/admin/providers/{provider['id']}")
    model_delete = await admin_client.delete(f"/admin/models/{model['id']}")
    route_delete = await admin_client.delete(f"/admin/model-routes/{route.json()['id']}")

    assert provider_delete.status_code == 409
    assert model_delete.status_code == 409
    assert route_delete.status_code == 409


async def test_catalog_records_without_history_can_be_deleted(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    provider = await _create_provider(admin_client)
    model = await _create_model(admin_client)
    route = await admin_client.post(
        "/admin/model-routes",
        json={
            "model_id": model["id"],
            "provider_id": provider["id"],
            "provider_protocol_id": provider["protocols"][0]["id"],
            "upstream_model": "native-original",
        },
    )
    assert route.status_code == 201, route.text

    route_delete = await admin_client.delete(f"/admin/model-routes/{route.json()['id']}")
    model_delete = await admin_client.delete(f"/admin/models/{model['id']}")
    provider_delete = await admin_client.delete(f"/admin/providers/{provider['id']}")

    assert route_delete.status_code == 204
    assert model_delete.status_code == 204
    assert provider_delete.status_code == 204
    assert await session.scalar(select(Provider).where(Provider.id == provider["id"])) is None


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/admin/providers", {"name": "blocked", "credential": {}, "protocols": []}),
        ("POST", "/admin/models", {"canonical_name": "blocked", "display_name": "Blocked"}),
        (
            "POST",
            "/admin/model-routes",
            {
                "model_id": 1,
                "provider_id": 1,
                "provider_protocol_id": 1,
                "upstream_model": "blocked",
            },
        ),
    ],
)
async def test_non_admin_cannot_administer_catalog(
    method: str,
    path: str,
    payload: dict[str, object],
    non_admin_client: AsyncClient,
) -> None:
    response = await non_admin_client.request(method, path, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"
