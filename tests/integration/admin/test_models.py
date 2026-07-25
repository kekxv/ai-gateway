"""Comprehensive integration tests for Model API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.db.models import User


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
