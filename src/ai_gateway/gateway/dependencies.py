from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.audit.service import AuditService
from ai_gateway.billing.service import BillingService
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.db.session import get_session
from ai_gateway.gateway.service import GatewayService


def get_gateway_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GatewayService:
    billing = getattr(request.app.state, "billing_service", None)
    audit = getattr(request.app.state, "audit_service", None)
    http_clients = getattr(request.app.state, "http_client_factory", None)
    if not isinstance(billing, BillingService):
        raise RuntimeError("application billing service is not configured")
    if not isinstance(audit, AuditService):
        raise RuntimeError("application audit service is not configured")
    if http_clients is None:
        raise RuntimeError("application HTTP client factory is not configured")
    return GatewayService(
        session=session,
        settings=settings,
        billing_service=billing,
        audit_service=audit,
        http_client_factory=http_clients,
    )
