from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def test_model_alias_is_never_stored_as_route_upstream_model(
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

    alias_response = await admin_client.post(
        "/admin/model-routes",
        json={**route_payload, "upstream_model": "fast-chat"},
    )
    created = await admin_client.post(
        "/admin/model-routes",
        json={**route_payload, "upstream_model": "gpt-4.1-mini-2026-07-01"},
    )

    assert alias_response.status_code == 422
    assert alias_response.json()["detail"]["code"] == "alias_not_allowed_upstream"
    assert created.status_code == 201, created.text
    stored = await session.get(ModelRoute, created.json()["id"])
    assert stored is not None
    assert stored.upstream_model == "gpt-4.1-mini-2026-07-01"


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
