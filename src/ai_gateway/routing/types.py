from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ai_gateway.core.enums import Protocol, RouteRuntimeState
from ai_gateway.core.errors import GatewayError


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    route_id: int
    model_id: int
    provider_id: int
    provider_protocol_id: int
    protocol: Protocol
    base_url: str
    websocket_url: str | None
    upstream_model: str
    weight: int
    supports_responses: bool = True
    runtime_state: RouteRuntimeState = RouteRuntimeState.CLOSED
    disabled_until: datetime | None = None
    provider_credential_encrypted: bytes = b""
    proxy_config_encrypted: bytes | None = None
    extra_headers_encrypted: bytes | None = None
    provider_public_multiplier: Decimal = Decimal("1.00")
    provider_cost_multiplier: Decimal = Decimal("1.00")

    @property
    def id(self) -> int:
        """Expose the underlying route identifier for ModelRoute-compatible callers."""
        return self.route_id

    @property
    def credential_encrypted(self) -> bytes:
        return self.provider_credential_encrypted


@dataclass(frozen=True, slots=True)
class RouteFailure:
    """Structured upstream failure accepted by the route health classifier."""

    status_code: int | None = None
    error_code: str | None = None
    exception: BaseException | None = None


class NoRouteAvailable(GatewayError):
    code = "no_route_available"
    status_code = 503

    def __init__(
        self,
        requested_model: str,
        *,
        removed_by_scope: bool = False,
        removed_by_transport: bool = False,
        removed_by_health: bool = False,
    ) -> None:
        self.requested_model = requested_model
        self.removed_by_scope = removed_by_scope
        self.removed_by_transport = removed_by_transport
        self.removed_by_health = removed_by_health
        self.diagnostics = {
            "api_key_scope": removed_by_scope,
            "transport_capability": removed_by_transport,
            "health_state": removed_by_health,
        }
        reasons = [
            label
            for removed, label in (
                (removed_by_scope, "API key scope"),
                (removed_by_transport, "transport capability"),
                (removed_by_health, "route health"),
            )
            if removed
        ]
        reason_text = f" ({', '.join(reasons)})" if reasons else ""
        super().__init__(f"No route is available for model {requested_model!r}{reason_text}")

    @property
    def scope_filtered(self) -> bool:
        return self.removed_by_scope

    @property
    def transport_filtered(self) -> bool:
        return self.removed_by_transport

    @property
    def health_filtered(self) -> bool:
        return self.removed_by_health

    @property
    def removed_by_api_key_scope(self) -> bool:
        return self.removed_by_scope

    @property
    def removed_by_transport_capability(self) -> bool:
        return self.removed_by_transport

    @property
    def removed_by_health_state(self) -> bool:
        return self.removed_by_health
