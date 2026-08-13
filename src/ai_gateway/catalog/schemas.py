from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, Any, Literal

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
from ai_gateway.core.enums import ModelType, Protocol, RouteRuntimeState, RouteSource
from ai_gateway.core.limits import MODEL_SELECTOR_MAX_LENGTH

CatalogName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MODEL_SELECTOR_MAX_LENGTH,
    ),
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
    canonical_name: str | None
    model_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.model_ids:
            object.__setattr__(self, "model_ids", (self.model_id,))


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
    cost_multiplier: PriceMultiplier = Decimal("1.00")
    public_multiplier: PriceMultiplier = Decimal("1.00")

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_price_multiplier(cls, value: Any) -> Any:
        return _provider_multiplier_fields(value)


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CatalogName | None = None
    credential: ProviderCredentialObject | None = None
    enabled: bool | None = None
    auto_load_models: bool | None = None
    model_sync_interval_seconds: int | None = Field(default=None, ge=1)
    protocols: list[ProviderProtocolInput] | None = None
    cost_multiplier: PriceMultiplier | None = None
    public_multiplier: PriceMultiplier | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_price_multiplier(cls, value: Any) -> Any:
        return _provider_multiplier_fields(value)


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
    cost_multiplier: Decimal
    public_multiplier: Decimal


class ModelAliasInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: CatalogName
    enabled: bool = True


AliasInput = CatalogName | ModelAliasInput


class ModelPriceTierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_input_tokens: int | None = Field(default=None, ge=1)
    input_price_per_million: Price
    output_price_per_million: Price
    cache_read_price_per_million: Price = Decimal("0")
    cache_write_price_per_million: Price = Decimal("0")


class ModelPriceTierResponse(ModelPriceTierInput):
    id: int


class ModelTimePriceRuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekdays: set[int] = Field(min_length=1)
    start_time: time
    end_time: time
    effective_at: datetime | None = None
    input_price_per_million: Price
    output_price_per_million: Price
    cache_read_price_per_million: Price = Decimal("0")
    cache_write_price_per_million: Price = Decimal("0")

    @model_validator(mode="after")
    def validate_time_range_and_weekdays(self) -> ModelTimePriceRuleInput:
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be later than start_time")
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("weekdays must contain values from 0 (Monday) to 6 (Sunday)")
        return self


class ModelTimePriceRuleResponse(ModelTimePriceRuleInput):
    id: int


class PublicModelPriceTierResponse(BaseModel):
    max_input_tokens: int | None
    input_price_per_million_min: Decimal
    input_price_per_million_max: Decimal
    output_price_per_million_min: Decimal
    output_price_per_million_max: Decimal
    cache_read_price_per_million_min: Decimal
    cache_read_price_per_million_max: Decimal
    cache_write_price_per_million_min: Decimal
    cache_write_price_per_million_max: Decimal


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: CatalogName
    display_name: CatalogName
    model_type: ModelType = ModelType.TEXT
    input_price_per_million: Price = Decimal("0")
    output_price_per_million: Price = Decimal("0")
    cache_read_price_per_million: Price = Decimal("0")
    cache_write_price_per_million: Price = Decimal("0")
    enabled: bool = True
    aliases: list[AliasInput] = Field(default_factory=list)
    routing_strategy: RoutingStrategy = "weighted_random"
    price_multiplier: PriceMultiplier = Decimal("1.00")
    price_tiers: list[ModelPriceTierInput] = Field(default_factory=list)
    time_price_rules: list[ModelTimePriceRuleInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_aliases(self) -> ModelCreate:
        _validate_unique_aliases(self.aliases)
        _validate_price_tiers(self.price_tiers)
        return self


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: CatalogName | None = None
    display_name: CatalogName | None = None
    model_type: ModelType | None = None
    input_price_per_million: Price | None = None
    output_price_per_million: Price | None = None
    cache_read_price_per_million: Price | None = None
    cache_write_price_per_million: Price | None = None
    enabled: bool | None = None
    aliases: list[AliasInput] | None = None
    routing_strategy: RoutingStrategy | None = None
    price_multiplier: PriceMultiplier | None = None
    price_tiers: list[ModelPriceTierInput] | None = None
    time_price_rules: list[ModelTimePriceRuleInput] | None = None

    @model_validator(mode="after")
    def validate_aliases(self) -> ModelUpdate:
        if self.aliases is not None:
            _validate_unique_aliases(self.aliases)
        if self.price_tiers is not None:
            _validate_price_tiers(self.price_tiers)
        return self


class ModelAliasResponse(BaseModel):
    id: int
    alias: str
    enabled: bool


class ModelResponse(BaseModel):
    id: int
    canonical_name: str
    display_name: str
    model_type: ModelType = ModelType.TEXT
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
    price_tiers: list[ModelPriceTierResponse]
    time_price_rules: list[ModelTimePriceRuleResponse] = Field(default_factory=list)


class UserModelResponse(BaseModel):
    id: int
    canonical_name: str
    display_name: str
    model_type: ModelType
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    cache_read_price_per_million: Decimal
    cache_write_price_per_million: Decimal
    price_multiplier: Decimal
    enabled: bool
    aliases: list[ModelAliasResponse]
    routing_strategy: RoutingStrategy
    created_at: datetime
    updated_at: datetime
    public_price_tiers: list[PublicModelPriceTierResponse]


class ModelRouteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: int = Field(ge=1)
    provider_id: int = Field(ge=1)
    upstream_model: CatalogName
    weight: int = Field(default=100, ge=1, le=10000)
    enabled: bool = True


class ModelRouteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: int | None = Field(default=None, ge=1)
    provider_id: int | None = Field(default=None, ge=1)
    upstream_model: CatalogName | None = None
    weight: int | None = Field(default=None, ge=1, le=10000)
    enabled: bool | None = None


class ModelRouteResponse(BaseModel):
    id: int
    model_id: int
    provider_id: int
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


def _validate_price_tiers(tiers: list[ModelPriceTierInput]) -> None:
    if not tiers:
        return
    if tiers[-1].max_input_tokens is not None:
        raise ValueError("the final model price tier must be unbounded")
    bounded = [tier.max_input_tokens for tier in tiers[:-1]]
    if any(limit is None for limit in bounded):
        raise ValueError("only the final model price tier may be unbounded")
    numeric = [limit for limit in bounded if limit is not None]
    if any(current <= previous for previous, current in zip(numeric, numeric[1:])):
        raise ValueError("model price tier limits must be strictly increasing")


def _provider_multiplier_fields(value: Any) -> Any:
    if not isinstance(value, dict) or "price_multiplier" not in value:
        return value
    normalized = dict(value)
    legacy = normalized.pop("price_multiplier")
    if "cost_multiplier" in normalized:
        raise ValueError("provide cost_multiplier or legacy price_multiplier, not both")
    normalized["cost_multiplier"] = legacy
    return normalized
