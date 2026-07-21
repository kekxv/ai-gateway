from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi import Depends, FastAPI
from fastapi.exceptions import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.api_key import (
    ApiKeyPrincipal,
    authenticate_api_key,
    get_api_key_principal,
)
from ai_gateway.db.models import ApiKey, Model, Provider, User
from ai_gateway.db.session import get_session


@pytest.fixture
def catalog_records() -> tuple[Provider, Provider, Model, Model]:
    return (
        Provider(name="provider-one", credential_encrypted=b"one", enabled=True),
        Provider(name="provider-two", credential_encrypted=b"two", enabled=True),
        Model(canonical_name="model-one", display_name="Model One", enabled=True),
        Model(canonical_name="model-two", display_name="Model Two", enabled=True),
    )


async def persist_catalog(
    session: AsyncSession,
    catalog_records: tuple[Provider, Provider, Model, Model],
) -> tuple[Provider, Provider, Model, Model]:
    session.add_all(catalog_records)
    await session.flush()
    return catalog_records


async def create_key(
    admin_client: AsyncClient,
    *,
    user_id: int,
    name: str = "production",
    scope: str = "all",
    provider_ids: list[int] | None = None,
    model_ids: list[int] | None = None,
    expires_at: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "user_id": user_id,
        "name": name,
        "scope": scope,
        "provider_ids": provider_ids or [],
        "model_ids": model_ids or [],
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at
    response = await admin_client.post("/admin/api-keys", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_created_api_key_is_returned_once_and_stored_as_digest(
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
    catalog_records: tuple[Provider, Provider, Model, Model],
) -> None:
    _, _, model, _ = await persist_catalog(session, catalog_records)

    created = await create_key(
        admin_client,
        user_id=regular_user_record.id,
        scope="models",
        model_ids=[model.id],
    )

    raw_key = created["key"]
    assert isinstance(raw_key, str)
    assert raw_key.startswith("sk-gw-")
    detail = await admin_client.get(f"/admin/api-keys/{created['id']}")
    listing = await admin_client.get("/admin/api-keys")
    assert detail.status_code == 200
    assert "key" not in detail.json()
    assert all("key" not in item for item in listing.json())
    stored = await session.get(ApiKey, created["id"])
    assert stored is not None
    assert stored.key_prefix == raw_key[:12]
    assert stored.key_hash == sha256(raw_key.encode()).digest()
    assert raw_key.encode() not in stored.key_hash


async def test_key_update_changes_metadata_and_relations_without_rotating_secret(
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
    catalog_records: tuple[Provider, Provider, Model, Model],
) -> None:
    provider_one, provider_two, model_one, model_two = await persist_catalog(
        session, catalog_records
    )
    created = await create_key(
        admin_client,
        user_id=regular_user_record.id,
        scope="providers_and_models",
        provider_ids=[provider_one.id],
        model_ids=[model_one.id],
    )
    raw_key = str(created["key"])
    original_hash = sha256(raw_key.encode()).digest()

    response = await admin_client.patch(
        f"/admin/api-keys/{created['id']}",
        json={
            "name": "updated",
            "scope": "providers_and_models",
            "is_active": True,
            "provider_ids": [provider_two.id],
            "model_ids": [model_two.id],
        },
    )

    assert response.status_code == 200
    assert "key" not in response.json()
    assert response.json()["provider_ids"] == [provider_two.id]
    assert response.json()["model_ids"] == [model_two.id]
    stored = await session.get(ApiKey, created["id"])
    assert stored is not None
    assert stored.key_hash == original_hash
    principal = await authenticate_api_key(raw_key, session)
    assert principal.provider_ids == frozenset({provider_two.id})
    assert principal.model_ids == frozenset({model_two.id})


async def test_rotation_revokes_old_key_and_returns_one_new_secret(
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
    catalog_records: tuple[Provider, Provider, Model, Model],
) -> None:
    provider, _, model, _ = await persist_catalog(session, catalog_records)
    created = await create_key(
        admin_client,
        user_id=regular_user_record.id,
        scope="providers_and_models",
        provider_ids=[provider.id],
        model_ids=[model.id],
    )
    old_key = str(created["key"])

    rotated = await admin_client.post(f"/admin/api-keys/{created['id']}/rotate")

    assert rotated.status_code == 201
    replacement = rotated.json()
    assert replacement["id"] != created["id"]
    assert replacement["key"].startswith("sk-gw-")
    assert replacement["provider_ids"] == [provider.id]
    assert replacement["model_ids"] == [model.id]
    old_record = await session.get(ApiKey, created["id"])
    assert old_record is not None
    assert old_record.is_active is False
    with pytest.raises(HTTPException) as old_error:
        await authenticate_api_key(old_key, session)
    assert getattr(old_error.value, "detail", {})["code"] == "invalid_api_key"
    new_principal = await authenticate_api_key(replacement["key"], session)
    assert new_principal.api_key_id == replacement["id"]


async def test_native_headers_accept_matching_credentials_and_reject_ambiguity(
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
) -> None:
    created = await create_key(admin_client, user_id=regular_user_record.id)
    raw_key = str(created["key"])
    app = _protected_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for headers in (
            {"Authorization": f"Bearer {raw_key}"},
            {"x-api-key": raw_key},
            {"x-goog-api-key": raw_key},
            {"Authorization": f"Bearer {raw_key}", "x-api-key": raw_key},
        ):
            response = await client.get("/protected", headers=headers)
            assert response.status_code == 200, response.text

        ambiguous = await client.get(
            "/protected",
            headers={"x-api-key": raw_key, "x-goog-api-key": "sk-gw-different"},
        )

    assert ambiguous.status_code == 400
    assert ambiguous.json()["detail"]["code"] == "ambiguous_credentials"


@pytest.mark.parametrize(
    "headers",
    [
        [("x-api-key", "{key}"), ("x-api-key", "{key}")],
        [("x-goog-api-key", "{key}"), ("x-goog-api-key", "{key}")],
        [
            ("Authorization", "Bearer {key}"),
            ("Authorization", "Bearer {key}"),
        ],
    ],
)
async def test_duplicate_same_name_credentials_accept_identical_values(
    headers: list[tuple[str, str]],
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
) -> None:
    created = await create_key(admin_client, user_id=regular_user_record.id)
    raw_key = str(created["key"])
    app = _protected_app(session)
    repeated_headers = [(name, value.format(key=raw_key)) for name, value in headers]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/protected", headers=repeated_headers)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "headers",
    [
        [("x-api-key", "{key}"), ("x-api-key", "sk-gw-different")],
        [("x-goog-api-key", "{key}"), ("x-goog-api-key", "sk-gw-different")],
        [
            ("Authorization", "Bearer {key}"),
            ("Authorization", "Bearer sk-gw-different"),
        ],
    ],
)
async def test_duplicate_same_name_credentials_reject_differing_values(
    headers: list[tuple[str, str]],
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
) -> None:
    created = await create_key(admin_client, user_id=regular_user_record.id)
    raw_key = str(created["key"])
    app = _protected_app(session)
    repeated_headers = [(name, value.format(key=raw_key)) for name, value in headers]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/protected", headers=repeated_headers)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ambiguous_credentials"


async def test_successful_authentication_persists_last_used_at(
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
) -> None:
    created = await create_key(admin_client, user_id=regular_user_record.id)
    stored = await session.get(ApiKey, created["id"])
    assert stored is not None
    assert stored.last_used_at is None

    await authenticate_api_key(str(created["key"]), session)
    await session.refresh(stored)

    assert stored.last_used_at is not None


@pytest.mark.parametrize(
    "relations",
    [
        {"provider_ids": [999_999]},
        {"model_ids": [999_999]},
    ],
)
async def test_api_key_rejects_invalid_scope_relation_ids(
    relations: dict[str, list[int]],
    admin_client: AsyncClient,
    regular_user_record: User,
) -> None:
    response = await admin_client.post(
        "/admin/api-keys",
        json={
            "user_id": regular_user_record.id,
            "name": "invalid-scope",
            "scope": "all",
            **relations,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_scope_reference"


async def test_deleted_api_key_is_removed_and_cannot_authenticate(
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
) -> None:
    created = await create_key(admin_client, user_id=regular_user_record.id)

    deleted = await admin_client.delete(f"/admin/api-keys/{created['id']}")
    detail = await admin_client.get(f"/admin/api-keys/{created['id']}")

    assert deleted.status_code == 204
    assert detail.status_code == 404
    with pytest.raises(HTTPException) as error:
        await authenticate_api_key(str(created["key"]), session)
    assert getattr(error.value, "detail", {})["code"] == "invalid_api_key"


@pytest.mark.parametrize("state", ["inactive", "expired", "inactive_user"])
async def test_inactive_expired_or_disabled_owner_fails_authentication(
    state: str,
    admin_client: AsyncClient,
    regular_user_record: User,
    session: AsyncSession,
) -> None:
    expires_at = None
    if state == "expired":
        expires_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    created = await create_key(
        admin_client,
        user_id=regular_user_record.id,
        expires_at=expires_at,
    )
    if state == "inactive":
        await admin_client.patch(
            f"/admin/api-keys/{created['id']}",
            json={"is_active": False},
        )
    if state == "inactive_user":
        regular_user_record.is_active = False
        await session.flush()

    with pytest.raises(HTTPException) as error:
        await authenticate_api_key(str(created["key"]), session)

    expected = "user_disabled" if state == "inactive_user" else "invalid_api_key"
    assert getattr(error.value, "detail", {})["code"] == expected


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/admin/api-keys", {"user_id": 1, "name": "blocked"}),
        ("PATCH", "/admin/api-keys/1", {"name": "blocked"}),
        ("DELETE", "/admin/api-keys/1", None),
        ("POST", "/admin/api-keys/1/rotate", None),
    ],
)
async def test_non_admin_cannot_mutate_api_keys(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    non_admin_client: AsyncClient,
) -> None:
    response = await non_admin_client.request(method, path, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"


async def test_non_admin_cannot_list_api_keys(non_admin_client: AsyncClient) -> None:
    response = await non_admin_client.get("/admin/api-keys")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"


def _protected_app(session: AsyncSession) -> FastAPI:
    app = FastAPI()

    async def override_session():  # type: ignore[no-untyped-def]
        yield session

    app.dependency_overrides[get_session] = override_session

    @app.get("/protected")
    async def protected(
        principal: ApiKeyPrincipal = Depends(get_api_key_principal),
    ) -> dict[str, int]:
        return {"api_key_id": principal.api_key_id}

    return app
