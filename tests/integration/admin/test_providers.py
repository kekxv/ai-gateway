"""Comprehensive integration tests for Provider API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_provider_price_multiplier_comprehensive_flow(
    admin_client: AsyncClient,
) -> None:
    """Comprehensive test of price_multiplier in Provider API."""

    # 1. Create without price_multiplier (should default to 1.00)
    create_response = await admin_client.post(
        "/admin/providers",
        json={
            "name": "test-provider",
            "credential": {"api_key": "test-secret"},
            "enabled": True,
            "protocols": [
                {
                    "protocol": "openai",
                    "base_url": "https://api.example.com/v1",
                    "enabled": True,
                }
            ],
        },
    )
    assert create_response.status_code == 201
    provider = create_response.json()
    assert provider["price_multiplier"] == "1.00"
    provider_id = provider["id"]

    # 2. Get provider returns price_multiplier
    get_response = await admin_client.get(f"/admin/providers/{provider_id}")
    assert get_response.status_code == 200
    assert get_response.json()["price_multiplier"] == "1.00"

    # 3. Update to 1.50
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "1.50"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_multiplier"] == "1.50"

    # 4. Update to boundary value 0.10
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "0.10"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_multiplier"] == "0.10"

    # 5. Update to boundary value 10.00
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "10.00"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_multiplier"] == "10.00"

    # 6. Validation rejects 0.09
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "0.09"},
    )
    assert update_response.status_code == 422

    # 7. Validation rejects 10.01
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "10.01"},
    )
    assert update_response.status_code == 422

    # 8. Update other fields doesn't change price_multiplier
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"name": "updated-provider"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price_multiplier"] == "10.00"  # Should remain unchanged

    # 9. List providers returns price_multiplier
    list_response = await admin_client.get("/admin/providers")
    assert list_response.status_code == 200
    providers = list_response.json()
    provider_in_list = next(p for p in providers if p["id"] == provider_id)
    assert provider_in_list["price_multiplier"] == "10.00"
