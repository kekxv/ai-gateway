"""Audit logging helpers for admin configuration changes."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.db.models import ConfigAuditLog


async def log_multiplier_change(
    session: AsyncSession,
    user_id: int,
    resource_type: str,
    resource_id: int,
    old_value: Decimal,
    new_value: Decimal,
) -> None:
    """Log price_multiplier change to audit trail.

    Args:
        session: Database session to use for the insert.
        user_id: ID of the user making the change.
        resource_type: Type of resource ("provider" or "model").
        resource_id: ID of the resource being changed.
        old_value: Previous price_multiplier value.
        new_value: New price_multiplier value.
    """
    audit_log = ConfigAuditLog(
        user_id=user_id,
        action=f"{resource_type}_price_multiplier_updated",
        resource_type=resource_type,
        resource_id=resource_id,
        old_value=str(old_value),
        new_value=str(new_value),
    )
    session.add(audit_log)
