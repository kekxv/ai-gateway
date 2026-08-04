"""Comprehensive integration tests for Model API endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_models_can_share_an_alias(admin_client: AsyncClient) -> None:
    """A shared alias must be assignable to more than one model."""
    model_a = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "shared-alias-model-a",
            "display_name": "Shared Alias Model A",
            "aliases": [{"alias": "shared-chat", "enabled": True}],
        },
    )
    model_b = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "shared-alias-model-b",
            "display_name": "Shared Alias Model B",
            "aliases": [{"alias": "shared-chat", "enabled": True}],
        },
    )

    assert model_a.status_code == 201, model_a.text
    assert model_b.status_code == 201, model_b.text


@pytest.mark.asyncio
async def test_admin_model_canonical_name_may_match_an_existing_alias(
    admin_client: AsyncClient,
) -> None:
    """A canonical model joins the weighted selector already exposed by an alias."""
    alias_owner = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "canonical-conflict-owner",
            "display_name": "Canonical Conflict Owner",
            "aliases": [{"alias": "canonical-conflict", "enabled": True}],
        },
    )
    matching_model = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "canonical-conflict",
            "display_name": "Matching Canonical Model",
        },
    )

    assert alias_owner.status_code == 201, alias_owner.text
    assert matching_model.status_code == 201, matching_model.text


@pytest.mark.asyncio
async def test_admin_model_alias_may_match_an_existing_canonical_name(
    admin_client: AsyncClient,
) -> None:
    canonical_owner = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "existing-canonical-selector",
            "display_name": "Existing Canonical Selector",
        },
    )
    alias_target = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "canonical-alias-target",
            "display_name": "Canonical Alias Target",
            "aliases": [{"alias": "existing-canonical-selector", "enabled": True}],
        },
    )

    assert canonical_owner.status_code == 201, canonical_owner.text
    assert alias_target.status_code == 201, alias_target.text


@pytest.mark.asyncio
async def test_admin_model_may_use_its_canonical_name_as_an_alias(
    admin_client: AsyncClient,
) -> None:
    created = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "self-alias-model",
            "display_name": "Self Alias Model",
            "aliases": [{"alias": "self-alias-model", "enabled": True}],
        },
    )

    assert created.status_code == 201, created.text
    assert [alias["alias"] for alias in created.json()["aliases"]] == ["self-alias-model"]


@pytest.mark.asyncio
async def test_admin_model_update_may_promote_its_previous_alias_to_canonical_name(
    admin_client: AsyncClient,
) -> None:
    """Renaming a model to one of its aliases preserves that alias."""
    created = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "alias-promotion-owner",
            "display_name": "Alias Promotion Owner",
            "aliases": [{"alias": "alias-promotion-target", "enabled": True}],
        },
    )
    assert created.status_code == 201, created.text

    updated = await admin_client.patch(
        f"/admin/models/{created.json()['id']}",
        json={"canonical_name": "alias-promotion-target"},
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["canonical_name"] == "alias-promotion-target"
    assert [alias["alias"] for alias in updated.json()["aliases"]] == [
        "alias-promotion-target"
    ]


@pytest.mark.asyncio
async def test_model_price_multiplier_comprehensive_flow(
    admin_client: AsyncClient,
) -> None:
    """Comprehensive test of price_multiplier in Model API."""

    # 1. Create without price_multiplier (should default to 1.00)
    create_response = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "test-model",
            "display_name": "Test Model",
            "enabled": True,
            "input_price_per_million": "10.00",
            "output_price_per_million": "20.00",
        },
    )
    assert create_response.status_code == 201, create_response.text
    model = create_response.json()
    assert model["price_multiplier"] == "1.00"
    model_id = model["id"]

    # 2. Get model returns price_multiplier
    get_response = await admin_client.get(f"/admin/models/{model_id}")
    assert get_response.status_code == 200
    assert get_response.json()["price_multiplier"] == "1.00"

    # 3. Update to 1.50
    update_response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "1.50"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_multiplier"] == "1.50"

    # 4. Update to boundary value 0.10
    update_response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "0.10"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_multiplier"] == "0.10"

    # 5. Update to boundary value 10.00
    update_response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "10.00"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_multiplier"] == "10.00"

    # 6. Validation rejects 0.09
    update_response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "0.09"},
    )
    assert update_response.status_code == 422

    # 7. Validation rejects 10.01
    update_response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "10.01"},
    )
    assert update_response.status_code == 422

    # 8. Update other fields doesn't change price_multiplier
    update_response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"display_name": "Updated Model"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_multiplier"] == "10.00"  # Should remain unchanged

    # 9. List models returns price_multiplier
    list_response = await admin_client.get("/admin/models")
    assert list_response.status_code == 200
    models = list_response.json()
    model_in_list = next(m for m in models if m["id"] == model_id)
    assert model_in_list["price_multiplier"] == "10.00"


async def test_model_price_tiers_round_trip_and_sync_legacy_prices(
    admin_client: AsyncClient,
) -> None:
    tiers = [
        {
            "max_input_tokens": 272000,
            "input_price_per_million": "1.00",
            "output_price_per_million": "2.00",
            "cache_read_price_per_million": "0.50",
            "cache_write_price_per_million": "0.75",
        },
        {
            "max_input_tokens": None,
            "input_price_per_million": "10.00",
            "output_price_per_million": "20.00",
            "cache_read_price_per_million": "5.00",
            "cache_write_price_per_million": "7.50",
        },
    ]

    created = await admin_client.post(
        "/admin/models",
        json={
            "canonical_name": "tiered-admin-model",
            "display_name": "Tiered Admin Model",
            "input_price_per_million": "99.00",
            "output_price_per_million": "99.00",
            "price_tiers": tiers,
        },
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["input_price_per_million"] == "1.00"
    assert body["output_price_per_million"] == "2.00"
    assert [tier["max_input_tokens"] for tier in body["price_tiers"]] == [272000, None]

    fetched = await admin_client.get(f"/admin/models/{body['id']}")
    assert fetched.status_code == 200, fetched.text
    fetched_tiers = fetched.json()["price_tiers"]
    assert [tier["id"] for tier in fetched_tiers] == [tier["id"] for tier in body["price_tiers"]]
    assert [tier["max_input_tokens"] for tier in fetched_tiers] == [272000, None]
    assert Decimal(fetched_tiers[0]["input_price_per_million"]) == Decimal("1.00")
