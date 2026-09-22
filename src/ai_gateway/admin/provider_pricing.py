"""Admin API and helpers for synchronizing upstream model prices.

new-api and one-api publish every model ratio they know about. This module
matches those ratios against the models routed through one provider and fills in
the prices that were never configured: an existing price is never overwritten,
because a price that an operator set by hand is a deliberate business decision.
Re-syncing such a model therefore stays a manual edit.

Prices are group independent, so they are filled from the published ratios alone.
The provider's ``cost_multiplier`` is a different field and only changes when the
operator selects one of the upstream groups: new-api bills a relay request with the
group of its *token* (``token.Group``, falling back to the account group), while
``GET /api/user/self`` reports the *account* group. Those can differ, so a group is
never guessed -- not from the account probe and not from a default group fallback.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated
from typing import Protocol as TypingProtocol

import httpx
import orjson
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.admin.audit import log_multiplier_change
from ai_gateway.admin.provider_balance import load_balance_config
from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.catalog.credentials import ProviderCredential
from ai_gateway.catalog.model_pricing import (
    ModelPriceError,
    UpstreamModelPrice,
    UpstreamPricing,
    fetch_upstream_pricing,
    group_ratio_for,
    truncate_price_error,
)
from ai_gateway.catalog.schemas import (
    ModelPriceSyncStatus,
    ProviderModelPriceRow,
    ProviderModelPriceSyncRequest,
    ProviderModelPriceSyncResult,
    ProviderUpstreamPricingPreview,
)
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol
from ai_gateway.core.logging import sanitize_log_event
from ai_gateway.core.security import decrypt_secret
from ai_gateway.db.models import (
    Model,
    ModelPriceTier,
    ModelRoute,
    ModelTimePriceRule,
    Provider,
    ProviderProtocol,
    User,
)
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/providers", tags=["admin-providers"])
logger = logging.getLogger("uvicorn")

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_MAX_UPSTREAM_ERROR_CHARS = 2048
_MULTIPLIER_QUANTUM = Decimal("0.01")
_MULTIPLIER_LIMIT = Decimal("99.99")

STATUS_UPDATED: ModelPriceSyncStatus = "updated"
STATUS_PRICED: ModelPriceSyncStatus = "priced"
STATUS_FIXED_PRICE: ModelPriceSyncStatus = "fixed_price"
STATUS_UNLISTED: ModelPriceSyncStatus = "unlisted"


class HttpClientProvider(TypingProtocol):
    async def client_for(
        self,
        url: str | httpx.URL,
        *,
        provider_id: int | None = None,
        proxy_config_encrypted: bytes | None = None,
    ) -> httpx.AsyncClient: ...


class PriceProviderNotFoundError(LookupError):
    pass


class ModelPriceSyncFailedError(RuntimeError):
    pass


class PriceGroupNotFoundError(ValueError):
    """The selected group is not part of the upstream ratio table."""


@dataclass(frozen=True, slots=True)
class _PriceSyncTarget:
    """A model routed through the provider, with the state needed to decide writes."""

    model_id: int
    model_name: str
    upstream_model: str
    has_prices: bool
    has_custom_pricing: bool
    current_input_price_per_million: Decimal
    current_output_price_per_million: Decimal

    @property
    def is_configured(self) -> bool:
        return self.has_prices or self.has_custom_pricing


@dataclass(frozen=True, slots=True)
class _PriceSyncContext:
    base_url: str
    protocol: Protocol
    credential: ProviderCredential
    group_credential: ProviderCredential | None
    user_id: str | None
    extra_headers: Mapping[str, str] | None
    proxy_config_encrypted: bytes | None
    targets: list[_PriceSyncTarget]


@dataclass(frozen=True, slots=True)
class _PriceSyncCounts:
    updated: int
    priced: int
    fixed_price: int
    unlisted: int


@router.post(
    "/{provider_id}/sync-model-prices",
    response_model=ProviderModelPriceSyncResult,
)
async def sync_provider_model_prices_endpoint(
    provider_id: int,
    request: Request,
    session: Session,
    admin: AdminUser,
    settings: AppSettings,
    payload: ProviderModelPriceSyncRequest | None = None,
) -> ProviderModelPriceSyncResult:
    http_client_factory = getattr(request.app.state, "http_client_factory", None)
    if http_client_factory is None:
        raise_auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "model_price_sync_unavailable",
            "Upstream price sync is unavailable",
        )
    try:
        return await sync_provider_model_prices(
            provider_id,
            session=session,
            http_client_factory=http_client_factory,
            settings=settings,
            actor_id=admin.id,
            group=payload.group if payload is not None else None,
            release_connection_before_query=True,
        )
    except PriceProviderNotFoundError:
        raise_auth_error(status.HTTP_404_NOT_FOUND, "provider_not_found", "Provider not found")
    except PriceGroupNotFoundError as exc:
        raise_auth_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_price_group", str(exc))
    except ModelPriceSyncFailedError as exc:
        raise_auth_error(status.HTTP_502_BAD_GATEWAY, "model_price_sync_failed", str(exc))


@router.get(
    "/{provider_id}/upstream-pricing",
    response_model=ProviderUpstreamPricingPreview,
)
async def preview_provider_upstream_pricing_endpoint(
    provider_id: int,
    request: Request,
    session: Session,
    admin: AdminUser,
    settings: AppSettings,
) -> ProviderUpstreamPricingPreview:
    http_client_factory = getattr(request.app.state, "http_client_factory", None)
    if http_client_factory is None:
        raise_auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "model_price_sync_unavailable",
            "Upstream price sync is unavailable",
        )
    try:
        return await preview_provider_upstream_pricing(
            provider_id,
            session=session,
            http_client_factory=http_client_factory,
            settings=settings,
            release_connection_before_query=True,
        )
    except PriceProviderNotFoundError:
        raise_auth_error(status.HTTP_404_NOT_FOUND, "provider_not_found", "Provider not found")
    except ModelPriceSyncFailedError as exc:
        raise_auth_error(status.HTTP_502_BAD_GATEWAY, "model_price_sync_failed", str(exc))


async def sync_provider_model_prices(
    provider_id: int,
    *,
    session: AsyncSession,
    http_client_factory: HttpClientProvider,
    settings: Settings,
    actor_id: int | None = None,
    group: str | None = None,
    release_connection_before_query: bool = False,
    log_failure: bool = True,
) -> ProviderModelPriceSyncResult:
    """Read the upstream price list once and fill in unconfigured model prices.

    ``group`` is only passed by the manual endpoint: it names the upstream group whose
    ratio becomes the provider cost multiplier. Without it the multiplier is untouched,
    which is what the automatic model sync relies on.
    """

    context = await _load_context(session, provider_id, settings)
    if not context.targets:
        return _empty_result(provider_id)
    if release_connection_before_query:
        await session.commit()

    client = await http_client_factory.client_for(
        context.base_url,
        provider_id=provider_id,
        proxy_config_encrypted=context.proxy_config_encrypted,
    )
    pricing = await _read_upstream_pricing(
        context,
        provider_id=provider_id,
        client=client,
        log_failure=log_failure,
        detect_group=False,
    )
    group_ratio = _selected_group_ratio(pricing.group_ratios, group)
    cost_multiplier = None if group_ratio is None else _quantize_multiplier(group_ratio)
    counts, pending = _plan_price_updates(context.targets, pricing.models)
    provider = await session.get(Provider, provider_id)
    if provider is None:
        raise PriceProviderNotFoundError(provider_id)
    multiplier_updated = (
        await _apply_cost_multiplier(session, provider, cost_multiplier, actor_id=actor_id)
        if cost_multiplier is not None
        else False
    )
    stored_multiplier = Decimal(str(provider.cost_multiplier))
    if pending:
        models = list(await session.scalars(select(Model).where(Model.id.in_(sorted(pending)))))
        for model in models:
            input_price, output_price = pending[model.id]
            model.input_price_per_million = input_price
            model.output_price_per_million = output_price
    await session.commit()

    return ProviderModelPriceSyncResult(
        provider_id=provider_id,
        group=group,
        group_ratio=group_ratio,
        cost_multiplier=stored_multiplier,
        cost_multiplier_updated=multiplier_updated,
        upstream_models=len(pricing.models),
        updated=counts.updated,
        priced=counts.priced,
        fixed_price=counts.fixed_price,
        unlisted=counts.unlisted,
        rows=_result_rows(context.targets, pricing.models),
    )


async def preview_provider_upstream_pricing(
    provider_id: int,
    *,
    session: AsyncSession,
    http_client_factory: HttpClientProvider,
    settings: Settings,
    release_connection_before_query: bool = False,
) -> ProviderUpstreamPricingPreview:
    """Describe what a price sync would do, without writing anything.

    The account group reported by ``/api/user/self`` is returned as a hint only: the
    operator picks the group whose ratio should become the cost multiplier.
    """

    context = await _load_context(session, provider_id, settings)
    if not context.targets:
        return ProviderUpstreamPricingPreview(provider_id=provider_id)
    if release_connection_before_query:
        await session.commit()

    client = await http_client_factory.client_for(
        context.base_url,
        provider_id=provider_id,
        proxy_config_encrypted=context.proxy_config_encrypted,
    )
    pricing = await _read_upstream_pricing(
        context,
        provider_id=provider_id,
        client=client,
        log_failure=False,
        detect_group=True,
    )
    counts, _pending = _plan_price_updates(context.targets, pricing.models)
    return ProviderUpstreamPricingPreview(
        provider_id=provider_id,
        detected_group=pricing.group,
        detected_group_ratio=pricing.group_ratio,
        group_ratios=dict(pricing.group_ratios),
        upstream_models=len(pricing.models),
        fillable=counts.updated,
        priced=counts.priced,
        fixed_price=counts.fixed_price,
        unlisted=counts.unlisted,
    )


async def fill_missing_model_prices(
    provider_id: int,
    *,
    session: AsyncSession,
    http_client_factory: HttpClientProvider,
    settings: Settings,
) -> ProviderModelPriceSyncResult | None:
    """Best-effort price fill for providers that publish new-api style prices.

    Providers without a price list are expected: the probe simply reports
    nothing to do, and the caller only counts what was filled.
    """

    try:
        return await sync_provider_model_prices(
            provider_id,
            session=session,
            http_client_factory=http_client_factory,
            settings=settings,
            log_failure=False,
        )
    except (PriceProviderNotFoundError, ModelPriceSyncFailedError, OSError, ValueError) as exc:
        logger.debug(
            "Skipped upstream price sync for provider_id=%d: %s",
            provider_id,
            sanitize_log_event(exc),
        )
        return None


async def _read_upstream_pricing(
    context: _PriceSyncContext,
    *,
    provider_id: int,
    client: httpx.AsyncClient,
    log_failure: bool,
    detect_group: bool,
) -> UpstreamPricing:
    try:
        return await fetch_upstream_pricing(
            base_url=context.base_url,
            credential=context.credential,
            group_credential=context.group_credential,
            protocol=context.protocol,
            user_id=context.user_id,
            extra_headers=context.extra_headers,
            detect_group=detect_group,
            client=client,
        )
    except (httpx.HTTPError, ModelPriceError, ValueError) as exc:
        message = _price_error_message(exc)
        if log_failure:
            logger.warning(
                "Provider price sync failed for provider_id=%d: %s: %s",
                provider_id,
                type(exc).__name__,
                sanitize_log_event(exc),
            )
        raise ModelPriceSyncFailedError(message) from exc


def _selected_group_ratio(
    group_ratios: Mapping[str, Decimal],
    group: str | None,
) -> Decimal | None:
    """Return the ratio of the group the operator selected, validating it exists."""

    if group is None:
        return None
    ratio = group_ratio_for(group_ratios, group)
    if ratio is None:
        listed = ", ".join(sorted(group_ratios)) or "none"
        raise PriceGroupNotFoundError(
            f"Upstream does not publish a ratio for group {group!r} (listed groups: {listed})"
        )
    if ratio <= 0:
        raise PriceGroupNotFoundError(
            f"Upstream reported an unusable ratio for group {group!r}: {ratio}"
        )
    return ratio


def _plan_price_updates(
    targets: list[_PriceSyncTarget],
    upstream_models: Mapping[str, UpstreamModelPrice],
) -> tuple[_PriceSyncCounts, dict[int, tuple[Decimal, Decimal]]]:
    counts: dict[ModelPriceSyncStatus, int] = {
        STATUS_UPDATED: 0,
        STATUS_PRICED: 0,
        STATUS_FIXED_PRICE: 0,
        STATUS_UNLISTED: 0,
    }
    pending: dict[int, tuple[Decimal, Decimal]] = {}
    for target in targets:
        entry = upstream_models.get(target.upstream_model)
        status = _target_status(target, entry)
        counts[status] += 1
        if status != STATUS_UPDATED or entry is None:
            continue
        if entry.input_price_per_million is None or entry.output_price_per_million is None:
            continue
        pending[target.model_id] = (entry.input_price_per_million, entry.output_price_per_million)
    return (
        _PriceSyncCounts(
            updated=counts[STATUS_UPDATED],
            priced=counts[STATUS_PRICED],
            fixed_price=counts[STATUS_FIXED_PRICE],
            unlisted=counts[STATUS_UNLISTED],
        ),
        pending,
    )


def _target_status(
    target: _PriceSyncTarget,
    entry: UpstreamModelPrice | None,
) -> ModelPriceSyncStatus:
    if entry is None:
        return STATUS_UNLISTED
    if not entry.is_token_priced:
        return STATUS_FIXED_PRICE
    if target.is_configured:
        return STATUS_PRICED
    return STATUS_UPDATED


def _result_rows(
    targets: list[_PriceSyncTarget],
    upstream_models: Mapping[str, UpstreamModelPrice],
) -> list[ProviderModelPriceRow]:
    rows: list[ProviderModelPriceRow] = []
    for target in targets:
        entry = upstream_models.get(target.upstream_model)
        rows.append(
            ProviderModelPriceRow(
                model_id=target.model_id,
                model_name=target.model_name,
                upstream_model=target.upstream_model,
                status=_target_status(target, entry),
                model_ratio=entry.model_ratio if entry is not None else None,
                completion_ratio=entry.completion_ratio if entry is not None else None,
                upstream_input_price_per_million=(
                    entry.input_price_per_million if entry is not None else None
                ),
                upstream_output_price_per_million=(
                    entry.output_price_per_million if entry is not None else None
                ),
                upstream_fixed_price=entry.fixed_price if entry is not None else None,
                current_input_price_per_million=target.current_input_price_per_million,
                current_output_price_per_million=target.current_output_price_per_million,
            )
        )
    return rows


async def _apply_cost_multiplier(
    session: AsyncSession,
    provider: Provider,
    cost_multiplier: Decimal | None,
    *,
    actor_id: int | None,
) -> bool:
    """Write the selected group ratio, reporting ratios the provider cannot store."""

    if cost_multiplier is None:
        logger.warning(
            "Ignored an out-of-range upstream group ratio for provider_id=%d",
            provider.id,
        )
        return False
    previous = Decimal(str(provider.cost_multiplier))
    if previous == cost_multiplier:
        return False
    provider.cost_multiplier = cost_multiplier
    if actor_id is not None:
        await log_multiplier_change(
            session=session,
            user_id=actor_id,
            resource_type="provider",
            resource_id=provider.id,
            old_value=previous,
            new_value=cost_multiplier,
            field_name="cost_multiplier",
        )
    return True


async def _load_context(
    session: AsyncSession,
    provider_id: int,
    settings: Settings,
) -> _PriceSyncContext:
    provider = await session.scalar(
        select(Provider).where(Provider.id == provider_id).options(selectinload(Provider.protocols))
    )
    if provider is None:
        raise PriceProviderNotFoundError(provider_id)
    protocol = _preferred_protocol(provider.protocols)
    if protocol is None:
        raise ModelPriceSyncFailedError("Provider has no enabled protocol to read prices from")
    credential = _provider_credential(provider, settings)
    balance_config = load_balance_config(provider, settings)
    return _PriceSyncContext(
        base_url=balance_config.base_url or protocol.base_url,
        protocol=protocol.protocol,
        credential=credential,
        group_credential=_group_credential(credential, balance_config.api_key),
        user_id=balance_config.user_id,
        extra_headers=_protocol_headers(protocol, settings),
        proxy_config_encrypted=(
            bytes(provider.proxy_config_encrypted)
            if provider.proxy_config_encrypted is not None
            else None
        ),
        targets=await _load_targets(session, provider_id),
    )


async def _load_targets(session: AsyncSession, provider_id: int) -> list[_PriceSyncTarget]:
    rows = (
        await session.execute(
            select(
                ModelRoute.model_id,
                ModelRoute.upstream_model,
                Model.canonical_name,
                Model.input_price_per_million,
                Model.output_price_per_million,
                Model.cache_read_price_per_million,
                Model.cache_write_price_per_million,
            )
            .join(Model, Model.id == ModelRoute.model_id)
            .where(ModelRoute.provider_id == provider_id)
            .order_by(ModelRoute.model_id)
        )
    ).all()
    if not rows:
        return []
    model_ids = [int(row.model_id) for row in rows]
    custom_ids = await _custom_pricing_model_ids(session, model_ids)
    return [
        _PriceSyncTarget(
            model_id=int(row.model_id),
            model_name=str(row.canonical_name),
            upstream_model=str(row.upstream_model),
            has_prices=any(
                Decimal(str(value)) != 0
                for value in (
                    row.input_price_per_million,
                    row.output_price_per_million,
                    row.cache_read_price_per_million,
                    row.cache_write_price_per_million,
                )
            ),
            has_custom_pricing=int(row.model_id) in custom_ids,
            current_input_price_per_million=Decimal(str(row.input_price_per_million)),
            current_output_price_per_million=Decimal(str(row.output_price_per_million)),
        )
        for row in rows
    ]


async def _custom_pricing_model_ids(session: AsyncSession, model_ids: list[int]) -> set[int]:
    tier_ids = set(
        await session.scalars(
            select(ModelPriceTier.model_id).where(ModelPriceTier.model_id.in_(model_ids)).distinct()
        )
    )
    rule_ids = set(
        await session.scalars(
            select(ModelTimePriceRule.model_id)
            .where(ModelTimePriceRule.model_id.in_(model_ids))
            .distinct()
        )
    )
    return {int(model_id) for model_id in tier_ids | rule_ids}


def _preferred_protocol(protocols: list[ProviderProtocol]) -> ProviderProtocol | None:
    enabled = [item for item in protocols if item.enabled]
    candidates = enabled or list(protocols)
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item.protocol is not Protocol.OPENAI, item.id))


def _provider_credential(provider: Provider, settings: Settings) -> ProviderCredential:
    try:
        values = orjson.loads(decrypt_secret(provider.credential_encrypted, settings=settings))
        if not isinstance(values, dict) or not all(isinstance(key, str) for key in values):
            raise ValueError("credential must be a JSON object")
        return ProviderCredential.from_mapping(values)
    except Exception:
        raise ModelPriceSyncFailedError("Provider credential could not be decoded") from None


def _group_credential(
    credential: ProviderCredential,
    api_key: str | None,
) -> ProviderCredential | None:
    """Reuse the balance query key, which is a console token able to report the group."""

    if not api_key:
        return None
    return replace(
        credential,
        api_key=api_key,
        auth_scheme=None if credential.auth_scheme == "none" else credential.auth_scheme,
    )


def _protocol_headers(
    protocol: ProviderProtocol,
    settings: Settings,
) -> dict[str, str] | None:
    encrypted = protocol.extra_headers_encrypted
    if encrypted is None:
        return None
    try:
        values = orjson.loads(decrypt_secret(bytes(encrypted), settings=settings))
    except Exception:
        logger.warning("Provider protocol headers could not be decoded")
        return None
    if not isinstance(values, dict):
        return None
    return {
        name: value
        for name, value in values.items()
        if isinstance(name, str) and isinstance(value, str)
    }


def _quantize_multiplier(value: Decimal) -> Decimal | None:
    quantized = value.quantize(_MULTIPLIER_QUANTUM, rounding=ROUND_HALF_UP)
    if quantized <= 0 or quantized > _MULTIPLIER_LIMIT:
        return None
    return quantized


def _empty_result(provider_id: int) -> ProviderModelPriceSyncResult:
    return ProviderModelPriceSyncResult(provider_id=provider_id, upstream_models=0, rows=[])


def _price_error_message(exc: httpx.HTTPError | ModelPriceError | ValueError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        status_label = f"{response.status_code} {response.reason_phrase}".strip()
        message = f"Upstream provider returned {status_label}"
        detail = _upstream_error_detail(response)
        if detail:
            message = f"{message}: {detail}"
    elif isinstance(exc, ModelPriceError):
        message = str(exc)
    else:
        detail = sanitize_log_event(exc).strip()
        message = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
    return truncate_price_error(message)


def _upstream_error_detail(response: httpx.Response) -> str:
    try:
        detail = orjson.dumps(response.json()).decode()
    except ValueError:
        detail = response.text.strip()
    detail = sanitize_log_event(detail)
    if len(detail) > _MAX_UPSTREAM_ERROR_CHARS:
        return f"{detail[:_MAX_UPSTREAM_ERROR_CHARS]}…"
    return detail
