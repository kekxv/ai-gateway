"""Integration tests for Model price_multiplier CRUD handling."""

from __future__ import annotations

from httpx import AsyncClient


async def _create_model(
    admin_client: AsyncClient,
    *,
    canonical_name: str = "test-model",
    price_multiplier: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "canonical_name": canonical_name,
        "display_name": "Test Model",
        "enabled": True,
        "input_price_per_million": "10.00",
        "output_price_per_million": "20.00",
    }
    if price_multiplier is not None:
        payload["price_multiplier"] = price_multiplier
    response = await admin_client.post("/admin/models", json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


async def test_create_model_with_price_multiplier(
    admin_client: AsyncClient,
) -> None:
    """Create model with price_multiplier."""
    model = await _create_model(admin_client, price_multiplier="1.50")
    assert model["price_multiplier"] == "1.50"


async def test_get_model_returns_price_multiplier(
    admin_client: AsyncClient,
) -> None:
    """Get model returns price_multiplier."""
    created = await _create_model(admin_client, price_multiplier="2.00")
    model_id = created["id"]

    response = await admin_client.get(f"/admin/models/{model_id}")
    assert response.status_code == 200
    model = response.json()
    assert model["price_multiplier"] == "2.00"


async def test_update_model_price_multiplier(
    admin_client: AsyncClient,
) -> None:
    """Update model price_multiplier."""
    created = await _create_model(admin_client, price_multiplier="1.00")
    model_id = created["id"]

    response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "1.80"},
    )
    assert response.status_code == 200
    model = response.json()
    assert model["price_multiplier"] == "1.80"


async def test_create_model_validates_price_multiplier_too_low(
    admin_client: AsyncClient,
) -> None:
    """Create model rejects price_multiplier below 0.10."""
    payload = {
        "canonical_name": "invalid-low",
        "display_name": "Invalid Low",
        "enabled": True,
        "input_price_per_million": "10.00",
        "output_price_per_million": "20.00",
        "price_multiplier": "0.05",
    }
    response = await admin_client.post("/admin/models", json=payload)
    assert response.status_code == 422


async def test_create_model_validates_price_multiplier_too_high(
    admin_client: AsyncClient,
) -> None:
    """Create model rejects price_multiplier above 10.00."""
    payload = {
        "canonical_name": "invalid-high",
        "display_name": "Invalid High",
        "enabled": True,
        "input_price_per_million": "10.00",
        "output_price_per_million": "20.00",
        "price_multiplier": "15.00",
    }
    response = await admin_client.post("/admin/models", json=payload)
    assert response.status_code == 422


async def test_update_model_validates_price_multiplier_too_low(
    admin_client: AsyncClient,
) -> None:
    """Update model rejects price_multiplier below 0.10."""
    created = await _create_model(admin_client, price_multiplier="1.00")
    model_id = created["id"]

    response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "0.05"},
    )
    assert response.status_code == 422


async def test_update_model_validates_price_multiplier_too_high(
    admin_client: AsyncClient,
) -> None:
    """Update model rejects price_multiplier above 10.00."""
    created = await _create_model(admin_client, price_multiplier="1.00")
    model_id = created["id"]

    response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "15.00"},
    )
    assert response.status_code == 422


async def test_create_model_price_multiplier_optional(
    admin_client: AsyncClient,
) -> None:
    """Create model works without price_multiplier (defaults to 1.00)."""
    model = await _create_model(admin_client)
    assert model["price_multiplier"] == "1.00"


async def test_update_model_price_multiplier_boundary_values(
    admin_client: AsyncClient,
) -> None:
    """Update model accepts boundary values 0.10 and 10.00."""
    created = await _create_model(admin_client, price_multiplier="1.00")
    model_id = created["id"]

    # Lower boundary
    response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "0.10"},
    )
    assert response.status_code == 200
    assert response.json()["price_multiplier"] == "0.10"

    # Upper boundary
    response = await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "10.00"},
    )
    assert response.status_code == 200
    assert response.json()["price_multiplier"] == "10.00"
