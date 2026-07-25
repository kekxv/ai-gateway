"""Integration tests for audit logging of price_multiplier changes."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.db.models import ConfigAuditLog, User


async def _create_provider(
    admin_client: AsyncClient,
    *,
    name: str = "audit-test-provider",
    price_multiplier: str = "1.00",
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
        "price_multiplier": price_multiplier,
    }
    response = await admin_client.post("/admin/providers", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _create_model(
    admin_client: AsyncClient,
    *,
    canonical_name: str = "audit-test-model",
    price_multiplier: str = "1.00",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "canonical_name": canonical_name,
        "display_name": "Audit Test Model",
        "enabled": True,
        "input_price_per_million": "10.00",
        "output_price_per_million": "20.00",
        "price_multiplier": price_multiplier,
    }
    response = await admin_client.post("/admin/models", json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


async def test_update_provider_price_multiplier_creates_audit_log(
    admin_client: AsyncClient,
    admin_user_record: User,
    session: AsyncSession,
) -> None:
    """Updating provider price_multiplier should create audit log."""
    provider = await _create_provider(admin_client, price_multiplier="1.00")
    provider_id = provider["id"]

    await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "1.50"},
    )

    result = await session.execute(
        select(ConfigAuditLog).where(
            ConfigAuditLog.resource_type == "provider",
            ConfigAuditLog.resource_id == provider_id,
            ConfigAuditLog.action == "provider_price_multiplier_updated",
        )
    )
    audit_logs = result.scalars().all()
    assert len(audit_logs) == 1
    assert audit_logs[0].old_value == "1.00"
    assert audit_logs[0].new_value == "1.50"
    assert audit_logs[0].user_id == admin_user_record.id


async def test_update_model_price_multiplier_creates_audit_log(
    admin_client: AsyncClient,
    admin_user_record: User,
    session: AsyncSession,
) -> None:
    """Updating model price_multiplier should create audit log."""
    model = await _create_model(admin_client, price_multiplier="1.00")
    model_id = model["id"]

    await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"price_multiplier": "2.00"},
    )

    result = await session.execute(
        select(ConfigAuditLog).where(
            ConfigAuditLog.resource_type == "model",
            ConfigAuditLog.resource_id == model_id,
            ConfigAuditLog.action == "model_price_multiplier_updated",
        )
    )
    audit_logs = result.scalars().all()
    assert len(audit_logs) == 1
    assert audit_logs[0].old_value == "1.00"
    assert audit_logs[0].new_value == "2.00"
    assert audit_logs[0].user_id == admin_user_record.id


async def test_no_audit_log_when_price_multiplier_unchanged_provider(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    """No audit log should be created when provider price_multiplier is not changed."""
    provider = await _create_provider(
        admin_client, name="no-audit-provider", price_multiplier="1.00"
    )
    provider_id = provider["id"]

    await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"name": "updated-provider"},
    )

    result = await session.execute(
        select(ConfigAuditLog).where(
            ConfigAuditLog.resource_type == "provider",
            ConfigAuditLog.resource_id == provider_id,
            ConfigAuditLog.action == "provider_price_multiplier_updated",
        )
    )
    audit_logs = result.scalars().all()
    assert len(audit_logs) == 0


async def test_no_audit_log_when_price_multiplier_unchanged_model(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    """No audit log should be created when model price_multiplier is not changed."""
    model = await _create_model(
        admin_client, canonical_name="no-audit-model", price_multiplier="1.00"
    )
    model_id = model["id"]

    await admin_client.patch(
        f"/admin/models/{model_id}",
        json={"display_name": "Updated Model"},
    )

    result = await session.execute(
        select(ConfigAuditLog).where(
            ConfigAuditLog.resource_type == "model",
            ConfigAuditLog.resource_id == model_id,
            ConfigAuditLog.action == "model_price_multiplier_updated",
        )
    )
    audit_logs = result.scalars().all()
    assert len(audit_logs) == 0


async def test_audit_log_captures_timestamp(
    admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Audit log should contain timestamp."""
    provider = await _create_provider(
        admin_client, name="timestamp-provider", price_multiplier="1.00"
    )
    provider_id = provider["id"]

    await admin_client.patch(
        f"/admin/providers/{provider_id}",
        json={"price_multiplier": "1.50"},
    )

    result = await session.execute(
        select(ConfigAuditLog).where(
            ConfigAuditLog.resource_type == "provider",
            ConfigAuditLog.resource_id == provider_id,
        )
    )
    audit_log = result.scalars().first()
    assert audit_log is not None
    assert audit_log.created_at is not None
