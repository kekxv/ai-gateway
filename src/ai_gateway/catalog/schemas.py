from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from ai_gateway.catalog.credentials import validate_provider_credential
from ai_gateway.core.enums import Protocol, RouteRuntimeState, RouteSource

CatalogName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
BaseUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]
WebsocketUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
]
JsonObject = dict[str, JsonValue]
ProviderCredentialObject = Annotated[JsonObject, AfterValidator(validate_provider_credential)]
Price = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=8)]
PriceMultiplier = Annotated[
    Decimal, Field(ge=Decimal("0.10"), le=Decimal("10.00"), max_digits=20, decimal_places=8)
]
RoutingStrategy = Literal["weighted_random"]


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    model_id: int
    requested_name: str
    canonical_name: str


class ProviderProtocolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = Field(default=None, ge=1)
    protocol: Protocol
    base_url: BaseUrl
    websocket_url: WebsocketUrl | None = None
    extra_headers: JsonObject | None = None
    supports_responses: bool = True
    enabled: bool = True


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CatalogName
    credential: ProviderCredentialObject = Field(default_factory=dict)
    enabled: bool = True
    auto_load_models: bool = False
    model_sync_interval_seconds: int | None = Field(default=None, ge=1)
    protocols: list[ProviderProtocolInput] = Field(default_factory=list)
    price_multiplier: PriceMultiplier = Decimal("1.00")


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CatalogName | None = None
    credential: ProviderCredentialObject | None = None
    enabled: bool | None = None
    auto_load_models: bool | None = None
    model_sync_interval_seconds: int | None = Field(default=None, ge=1)
    protocols: list[ProviderProtocolInput] | None = None
    price_multiplier: PriceMultiplier | None = None


class ProviderProtocolResponse(BaseModel):
    id: int
    protocol: Protocol
    base_url: str
    websocket_url: str | None
    has_extra_headers: bool
    supports_responses: bool
    enabled: bool


class ProviderResponse(BaseModel):
    id: int
    name: str
    has_credential: bool
    enabled: bool
    auto_load_models: bool
    model_sync_interval_seconds: int
    last_model_sync_at: datetime | None
    protocols: list[ProviderProtocolResponse]
    price_multiplier: Decimal


class ModelAliasInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: CatalogName
    enabled: bool = True


AliasInput = CatalogName | ModelAliasInput


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: CatalogName
    display_name: CatalogName
    input_price_per_million: Price = Decimal("0")
    output_price_per_million: Price = Decimal("0")
    cache_read_price_per_million: Price = Decimal("0")
    cache_write_price_per_million: Price = Decimal("0")
    enabled: bool = True
    aliases: list[AliasInput] = Field(default_factory=list)
    routing_strategy: RoutingStrategy = "weighted_random"
    price_multiplier: PriceMultiplier = Decimal("1.00")

    @model_validator(mode="after")
    def validate_aliases(self) -> ModelCreate:
        _validate_unique_aliases(self.aliases)
        return self


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: CatalogName | None = None
    display_name: CatalogName | None = None
    input_price_per_million: Price | None = None
    output_price_per_million: Price | None = None
    cache_read_price_per_million: Price | None = None
    cache_write_price_per_million: Price | None = None
    enabled: bool | None = None
    aliases: list[AliasInput] | None = None
    routing_strategy: RoutingStrategy | None = None
    price_multiplier: PriceMultiplier | None = None

    @model_validator(mode="after")
    def validate_aliases(self) -> ModelUpdate:
        if self.aliases is not None:
            _validate_unique_aliases(self.aliases)
        return self


class ModelAliasResponse(BaseModel):
    id: int
    alias: str
    enabled: bool


class ModelResponse(BaseModel):
    id: int
    canonical_name: str
    display_name: str
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    cache_read_price_per_million: Decimal
    cache_write_price_per_million: Decimal
    enabled: bool
    aliases: list[ModelAliasResponse]
    routing_strategy: RoutingStrategy
    created_at: datetime
    updated_at: datetime
    price_multiplier: Decimal


class ModelRouteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: int = Field(ge=1)
    provider_id: int = Field(ge=1)
    provider_protocol_id: int = Field(ge=1)
    upstream_model: CatalogName
    weight: int = Field(default=100, ge=1, le=10000)
    enabled: bool = True


class ModelRouteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: int | None = Field(default=None, ge=1)
    provider_id: int | None = Field(default=None, ge=1)
    provider_protocol_id: int | None = Field(default=None, ge=1)
    upstream_model: CatalogName | None = None
    weight: int | None = Field(default=None, ge=1, le=10000)
    enabled: bool | None = None


class ModelRouteResponse(BaseModel):
    id: int
    model_id: int
    provider_id: int
    provider_protocol_id: int
    upstream_model: str
    weight: int
    enabled: bool
    source: RouteSource
    runtime_state: RouteRuntimeState
    consecutive_failures: int
    disabled_until: datetime | None
    last_error_code: str | None
    last_error_at: datetime | None


def alias_values(aliases: list[AliasInput]) -> list[ModelAliasInput]:
    return [ModelAliasInput(alias=alias) if isinstance(alias, str) else alias for alias in aliases]


def _validate_unique_aliases(aliases: list[AliasInput]) -> None:
    values = [alias if isinstance(alias, str) else alias.alias for alias in aliases]
    if len(values) != len(set(values)):
        raise ValueError("model aliases must be unique")
