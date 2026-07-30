"""Comprehensive integration tests for Provider API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_provider_dual_multiplier_comprehensive_flow(
    admin_client: AsyncClient,
) -> None:
    """Comprehensive test of independent provider multipliers in the API."""

    # 1. Create without multipliers (both should default to 1.00)
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
    assert provider["cost_multiplier"] == "1.00"
    assert provider["public_multiplier"] == "1.00"
    assert "price_multiplier" not in provider
    provider_id = provider["id"]

    # 2. Get provider returns both explicit multipliers
    get_response = await admin_client.get(f"/admin/providers/{provider_id}")
    assert get_response.status_code == 200
    assert get_response.json()["cost_multiplier"] == "1.00"
    assert get_response.json()["public_multiplier"] == "1.00"

    # 3. Update to 1.50
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"cost_multiplier": "1.50", "public_multiplier": "2.00"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["cost_multiplier"] == "1.50"
    assert update_response.json()["public_multiplier"] == "2.00"

    # 4. Update to boundary value 0.10
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"cost_multiplier": "0.10"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["cost_multiplier"] == "0.10"
    assert update_response.json()["public_multiplier"] == "2.00"

    # 5. Update to boundary value 10.00
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"cost_multiplier": "10.00"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["cost_multiplier"] == "10.00"

    # 6. Validation rejects 0.09
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"cost_multiplier": "0.09"},
    )
    assert update_response.status_code == 422

    # 7. Validation rejects 10.01
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"cost_multiplier": "10.01"},
    )
    assert update_response.status_code == 422

    # 8. Updating other fields does not change either multiplier
    update_response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"name": "updated-provider"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["cost_multiplier"] == "10.00"
    assert update_response.json()["public_multiplier"] == "2.00"

    # 9. List providers returns both explicit multipliers
    list_response = await admin_client.get("/admin/providers")
    assert list_response.status_code == 200
    providers = list_response.json()
    provider_in_list = next(p for p in providers if p["id"] == provider_id)
    assert provider_in_list["cost_multiplier"] == "10.00"
    assert provider_in_list["public_multiplier"] == "2.00"
