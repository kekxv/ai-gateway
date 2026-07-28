from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.db.models import ApiKey, Model, ModelAlias, User


async def test_regular_user_sees_only_enabled_models_and_aliases(
    admin_client: AsyncClient,
    non_admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    available = Model(
        canonical_name="available-model",
        display_name="Available model",
        enabled=True,
        aliases=[
            ModelAlias(alias="available-alias", enabled=True),
            ModelAlias(alias="disabled-alias", enabled=False),
        ],
    )
    unavailable = Model(
        canonical_name="disabled-model",
        display_name="Disabled model",
        enabled=False,
        aliases=[ModelAlias(alias="hidden-alias", enabled=True)],
    )
    session.add_all([available, unavailable])
    await session.flush()

    user_response = await non_admin_client.get("/user/models")
    admin_response = await admin_client.get("/admin/models")

    assert user_response.status_code == 200
    assert [model["canonical_name"] for model in user_response.json()] == ["available-model"]
    assert [alias["alias"] for alias in user_response.json()[0]["aliases"]] == ["available-alias"]
    assert [model["canonical_name"] for model in admin_response.json()] == [
        "available-model",
        "disabled-model",
    ]
    assert [alias["alias"] for alias in admin_response.json()[0]["aliases"]] == [
        "available-alias",
        "disabled-alias",
    ]


async def test_regular_user_creates_and_lists_only_owned_api_keys(
    non_admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
) -> None:
    model = Model(
        canonical_name="personal-key-model",
        display_name="Personal key model",
        enabled=True,
    )
    session.add(model)
    await session.flush()

    created = await non_admin_client.post(
        "/user/api-keys",
        json={"name": "personal", "scope": "models", "model_ids": [model.id]},
    )
    listing = await non_admin_client.get("/user/api-keys")

    assert created.status_code == 201
    assert created.json()["user_id"] == regular_user_record.id
    assert created.json()["key"].startswith("sk-gw-")
    assert created.json()["model_ids"] == [model.id]
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [created.json()["id"]]
    assert "key" not in listing.json()[0]
    stored = await session.scalar(select(ApiKey).where(ApiKey.id == created.json()["id"]))
    assert stored is not None
    assert stored.user_id == regular_user_record.id


async def test_regular_user_updates_rotates_and_deletes_owned_api_key(
    non_admin_client: AsyncClient,
) -> None:
    created = await non_admin_client.post(
        "/user/api-keys",
        json={"name": "lifecycle", "scope": "all"},
    )
    assert created.status_code == 201
    key_id = created.json()["id"]

    detail = await non_admin_client.get(f"/user/api-keys/{key_id}")
    updated = await non_admin_client.patch(
        f"/user/api-keys/{key_id}",
        json={"name": "updated-lifecycle", "is_active": True},
    )
    rotated = await non_admin_client.post(f"/user/api-keys/{key_id}/rotate")
    deleted = await non_admin_client.delete(f"/user/api-keys/{rotated.json()['id']}")
    listing = await non_admin_client.get("/user/api-keys")

    assert detail.status_code == 200
    assert "key" not in detail.json()
    assert updated.status_code == 200
    assert updated.json()["name"] == "updated-lifecycle"
    assert rotated.status_code == 201
    assert rotated.json()["id"] != key_id
    assert rotated.json()["key"].startswith("sk-gw-")
    assert deleted.status_code == 204
    assert [(item["id"], item["is_active"]) for item in listing.json()] == [(key_id, False)]


async def test_regular_user_cannot_discover_or_mutate_another_users_api_key(
    admin_client: AsyncClient,
    non_admin_client: AsyncClient,
    admin_user_record: User,
) -> None:
    created = await admin_client.post(
        "/admin/api-keys",
        json={"user_id": admin_user_record.id, "name": "administrator-key"},
    )
    key_id = created.json()["id"]

    listing = await non_admin_client.get("/user/api-keys")
    responses = [
        await non_admin_client.get(f"/user/api-keys/{key_id}"),
        await non_admin_client.patch(
            f"/user/api-keys/{key_id}",
            json={"name": "stolen"},
        ),
        await non_admin_client.post(f"/user/api-keys/{key_id}/rotate"),
        await non_admin_client.delete(f"/user/api-keys/{key_id}"),
    ]

    assert listing.status_code == 200
    assert listing.json() == []
    assert [
        (response.status_code, response.json()["detail"]["code"]) for response in responses
    ] == [
        (404, "api_key_not_found"),
        (404, "api_key_not_found"),
        (404, "api_key_not_found"),
        (404, "api_key_not_found"),
    ]


async def test_regular_user_api_key_payload_rejects_owner_provider_scope_and_disabled_models(
    non_admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
) -> None:
    disabled_model = Model(
        canonical_name="disabled-key-model",
        display_name="Disabled key model",
        enabled=False,
    )
    session.add(disabled_model)
    await session.flush()

    owner = await non_admin_client.post(
        "/user/api-keys",
        json={"name": "owner", "user_id": regular_user_record.id},
    )
    provider_ids = await non_admin_client.post(
        "/user/api-keys",
        json={"name": "provider-ids", "provider_ids": [1]},
    )
    provider_scope = await non_admin_client.post(
        "/user/api-keys",
        json={"name": "provider-scope", "scope": "providers"},
    )
    disabled_model_scope = await non_admin_client.post(
        "/user/api-keys",
        json={
            "name": "disabled-model",
            "scope": "models",
            "model_ids": [disabled_model.id],
        },
    )

    assert owner.status_code == 422
    assert provider_ids.status_code == 422
    assert provider_scope.status_code == 422
    assert disabled_model_scope.status_code == 422
    assert disabled_model_scope.json()["detail"]["code"] == "invalid_scope_reference"
