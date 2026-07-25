"""Integration tests for Provider price_multiplier CRUD handling."""

from __future__ import annotations

from httpx import AsyncClient


async def _create_provider(
    admin_client: AsyncClient,
    *,
    name: str = "test-provider",
    price_multiplier: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "credential": {"api_key": "test-secret"},
        "enabled": True,
        "protocols": [
            {
                "protocol": "openai",
                "base_url": "https://api.example.com/v1",
                "enabled": True,
            }
        ],
    }
    if price_multiplier is not None:
        payload["price_multiplier"] = price_multiplier
    response = await admin_client.post("/admin/providers", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_provider_with_price_multiplier(
    admin_client: AsyncClient,
) -> None:
    """Create provider with explicit price_multiplier."""
    provider = await _create_provider(admin_client, price_multiplier="1.50")
    assert provider["price_multiplier"] == "1.50"


async def test_get_provider_returns_price_multiplier(
    admin_client: AsyncClient,
) -> None:
    """Get provider returns price_multiplier."""
    created = await _create_provider(admin_client, price_multiplier="2.00")
    provider_id = created["id"]

    response = await admin_client.get(f"/admin/providers/{provider_id}")
    assert response.status_code == 200
    provider = response.json()
    assert provider["price_multiplier"] == "2.00"


async def test_list_providers_returns_price_multiplier(
    admin_client: AsyncClient,
) -> None:
    """List providers returns price_multiplier for each provider."""
    await _create_provider(admin_client, name="pm-list-test", price_multiplier="1.25")

    response = await admin_client.get("/admin/providers")
    assert response.status_code == 200
    providers = response.json()
    match = [p for p in providers if p["name"] == "pm-list-test"]
    assert len(match) == 1
    assert match[0]["price_multiplier"] == "1.25"


async def test_update_provider_price_multiplier(
    admin_client: AsyncClient,
) -> None:
    """Update provider price_multiplier via PATCH."""
    created = await _create_provider(admin_client, price_multiplier="1.00")
    provider_id = created["id"]

    response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "1.80"},
    )
    assert response.status_code == 200
    provider = response.json()
    assert provider["price_multiplier"] == "1.80"


async def test_create_provider_validates_price_multiplier_too_low(
    admin_client: AsyncClient,
) -> None:
    """Create provider rejects price_multiplier below 0.10."""
    payload = {
        "name": "invalid-low",
        "credential": {"api_key": "test"},
        "enabled": True,
        "price_multiplier": "0.05",
        "protocols": [],
    }
    response = await admin_client.post("/admin/providers", json=payload)
    assert response.status_code == 422


async def test_create_provider_validates_price_multiplier_too_high(
    admin_client: AsyncClient,
) -> None:
    """Create provider rejects price_multiplier above 10.00."""
    payload = {
        "name": "invalid-high",
        "credential": {"api_key": "test"},
        "enabled": True,
        "price_multiplier": "15.00",
        "protocols": [],
    }
    response = await admin_client.post("/admin/providers", json=payload)
    assert response.status_code == 422


async def test_update_provider_validates_price_multiplier_too_low(
    admin_client: AsyncClient,
) -> None:
    """Update provider rejects price_multiplier below 0.10."""
    created = await _create_provider(admin_client, price_multiplier="1.00")
    provider_id = created["id"]

    response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "0.05"},
    )
    assert response.status_code == 422


async def test_update_provider_validates_price_multiplier_too_high(
    admin_client: AsyncClient,
) -> None:
    """Update provider rejects price_multiplier above 10.00."""
    created = await _create_provider(admin_client, price_multiplier="1.00")
    provider_id = created["id"]

    response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "15.00"},
    )
    assert response.status_code == 422


async def test_create_provider_price_multiplier_optional(
    admin_client: AsyncClient,
) -> None:
    """Create provider works without price_multiplier (defaults to 1.00)."""
    provider = await _create_provider(admin_client)
    assert provider["price_multiplier"] == "1.00"


async def test_update_provider_price_multiplier_boundary_values(
    admin_client: AsyncClient,
) -> None:
    """Update provider accepts boundary values 0.10 and 10.00."""
    created = await _create_provider(admin_client, price_multiplier="1.00")
    provider_id = created["id"]

    # Lower boundary
    response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "0.10"},
    )
    assert response.status_code == 200
    assert response.json()["price_multiplier"] == "0.10"

    # Upper boundary
    response = await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "10.00"},
    )
    assert response.status_code == 200
    assert response.json()["price_multiplier"] == "10.00"
