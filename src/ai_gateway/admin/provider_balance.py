"""Admin API and helpers for provider upstream balance queries."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, NoReturn, cast
from typing import Protocol as TypingProtocol

import httpx
import orjson
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.audit.redaction import redact_json
from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.catalog.balance import (
    BalanceConfigError,
    BalanceProbe,
    BalanceQueryConfig,
    BalanceQueryError,
    BalanceResult,
    detect_balance_types,
    query_balance,
    truncate_balance_error,
    validate_balance_config,
)
from ai_gateway.catalog.schemas import (
    ProviderBalanceCandidate,
    ProviderBalanceConfigInput,
    ProviderBalanceConfigResponse,
    ProviderBalanceDetectionResult,
    ProviderBalanceResponse,
    ProviderBalanceSyncResult,
)
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import BalanceQueryType, Protocol
from ai_gateway.core.logging import sanitize_log_event
from ai_gateway.core.security import decrypt_secret, encrypt_secret
from ai_gateway.db.models import Provider, ProviderProtocol, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/providers", tags=["admin-providers"])
logger = logging.getLogger("uvicorn")

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Clock = Callable[[], datetime]

_MAX_UPSTREAM_ERROR_CHARS = 2048
_QUERY_FAILURES = (httpx.HTTPError, BalanceQueryError, BalanceConfigError, ValueError)


class HttpClientProvider(TypingProtocol):
    async def client_for(
        self,
        url: str | httpx.URL,
        *,
        provider_id: int | None = None,
        proxy_config_encrypted: bytes | None = None,
    ) -> httpx.AsyncClient: ...


class BalanceProviderNotFoundError(LookupError):
    pass


class BalanceNotConfiguredError(RuntimeError):
    pass


class BalanceSyncFailedError(RuntimeError):
    pass


class BalanceDetectionFailedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _BalanceRecord:
    provider: Provider
    config: BalanceQueryConfig
    protocol: ProviderProtocol | None


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.post("/{provider_id}/balance/sync", response_model=ProviderBalanceSyncResult)
async def sync_provider_balance_endpoint(
    provider_id: int,
    request: Request,
    session: Session,
    _: AdminUser,
    settings: AppSettings,
) -> ProviderBalanceSyncResult:
    http_client_factory = _http_client_factory(request)
    try:
        return await sync_provider_balance(
            provider_id,
            session=session,
            http_client_factory=http_client_factory,
            settings=settings,
            release_connection_before_query=True,
        )
    except BalanceProviderNotFoundError:
        raise_auth_error(status.HTTP_404_NOT_FOUND, "provider_not_found", "Provider not found")
    except BalanceNotConfiguredError:
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "balance_query_not_configured",
            "Configure or detect the upstream balance type before syncing the balance",
        )
    except BalanceSyncFailedError as exc:
        raise_auth_error(status.HTTP_502_BAD_GATEWAY, "balance_sync_failed", str(exc))


@router.post("/{provider_id}/balance/detect", response_model=ProviderBalanceDetectionResult)
async def detect_provider_balance_endpoint(
    provider_id: int,
    request: Request,
    session: Session,
    _: AdminUser,
    settings: AppSettings,
) -> ProviderBalanceDetectionResult:
    http_client_factory = _http_client_factory(request)
    try:
        return await detect_provider_balance(
            provider_id,
            session=session,
            http_client_factory=http_client_factory,
            settings=settings,
            release_connection_before_query=True,
        )
    except BalanceProviderNotFoundError:
        raise_auth_error(status.HTTP_404_NOT_FOUND, "provider_not_found", "Provider not found")
    except BalanceDetectionFailedError as exc:
        raise_auth_error(status.HTTP_502_BAD_GATEWAY, "balance_detection_failed", str(exc))


def _http_client_factory(request: Request) -> HttpClientProvider:
    http_client_factory = getattr(request.app.state, "http_client_factory", None)
    if http_client_factory is None:
        raise_auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "balance_query_unavailable",
            "Balance queries are unavailable",
        )
    return cast(HttpClientProvider, http_client_factory)


async def sync_provider_balance(
    provider_id: int,
    *,
    session: AsyncSession,
    http_client_factory: HttpClientProvider,
    settings: Settings,
    clock: Clock = _utcnow,
    release_connection_before_query: bool = False,
) -> ProviderBalanceSyncResult:
    """Read the upstream balance once and persist the outcome."""

    record = await _load_balance_record(session, provider_id, settings)
    query_type = record.provider.balance_query_type
    if query_type is None:
        raise BalanceNotConfiguredError(provider_id)
    probe = balance_probe(record, settings)
    if release_connection_before_query:
        await session.commit()
    client = await _client_for(http_client_factory, record.provider, probe)
    try:
        result = await query_balance(probe, query_type, client=client, settings=settings)
    except _QUERY_FAILURES as exc:
        message = _balance_error_message(exc, query_type=query_type)
        logger.warning(
            "Provider balance query failed for provider_id=%d: %s: %s",
            provider_id,
            type(exc).__name__,
            sanitize_log_event(exc),
        )
        record.provider.balance_error = truncate_balance_error(message)
        record.provider.last_balance_sync_at = clock()
        await session.commit()
        raise BalanceSyncFailedError(message) from exc

    now = clock()
    _store_balance(record.provider, result, now)
    await session.commit()
    return ProviderBalanceSyncResult(
        provider_id=provider_id,
        query_type=result.query_type,
        amount=result.amount,
        currency=result.currency,
        used=result.used,
        is_available=result.is_available,
        synced_at=now,
    )


async def detect_provider_balance(
    provider_id: int,
    *,
    session: AsyncSession,
    http_client_factory: HttpClientProvider,
    settings: Settings,
    clock: Clock = _utcnow,
    release_connection_before_query: bool = False,
) -> ProviderBalanceDetectionResult:
    """Probe every built-in upstream API and auto-select an unambiguous match."""

    record = await _load_balance_record(session, provider_id, settings)
    probe = balance_probe(record, settings)
    if release_connection_before_query:
        await session.commit()
    client = await _client_for(http_client_factory, record.provider, probe)
    failures: dict[BalanceQueryType, BaseException] = {}
    resolved = await detect_balance_types(
        probe,
        client=client,
        settings=settings,
        failures=failures,
    )
    candidates = [
        ProviderBalanceCandidate(
            query_type=item.query_type,
            amount=item.amount,
            currency=item.currency,
            used=item.used,
            is_available=item.is_available,
        )
        for item in resolved
    ]
    if not candidates:
        logger.warning(
            "Provider balance detection found no upstream API for provider_id=%d", provider_id
        )
        raise BalanceDetectionFailedError(_balance_detection_message(failures))

    applied: BalanceQueryType | None = None
    if len(resolved) == 1:
        applied = resolved[0].query_type
        now = clock()
        record.provider.balance_query_type = applied
        _store_balance(record.provider, resolved[0], now)
        await session.commit()
    return ProviderBalanceDetectionResult(
        provider_id=provider_id,
        candidates=candidates,
        applied=applied,
    )


async def _client_for(
    http_client_factory: HttpClientProvider,
    provider: Provider,
    probe: BalanceProbe,
) -> httpx.AsyncClient:
    return await http_client_factory.client_for(
        probe.config.base_url or probe.base_url,
        provider_id=provider.id,
        proxy_config_encrypted=provider.proxy_config_encrypted,
    )


async def _load_balance_record(
    session: AsyncSession,
    provider_id: int,
    settings: Settings,
) -> _BalanceRecord:
    provider = await session.scalar(
        select(Provider).where(Provider.id == provider_id).options(selectinload(Provider.protocols))
    )
    if provider is None:
        raise BalanceProviderNotFoundError(provider_id)
    return _BalanceRecord(
        provider=provider,
        config=load_balance_config(provider, settings),
        protocol=_preferred_balance_protocol(provider.protocols),
    )


def _preferred_balance_protocol(protocols: list[ProviderProtocol]) -> ProviderProtocol | None:
    enabled = [item for item in protocols if item.enabled]
    candidates = enabled or list(protocols)
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item.protocol is not Protocol.OPENAI, item.id))


def balance_probe(record: _BalanceRecord, settings: Settings) -> BalanceProbe:
    protocol = record.protocol
    return BalanceProbe(
        base_url=record.config.base_url or (protocol.base_url if protocol is not None else ""),
        credential_encrypted=bytes(record.provider.credential_encrypted),
        protocol=protocol.protocol if protocol is not None else Protocol.OPENAI,
        config=record.config,
        extra_headers_encrypted=(
            bytes(protocol.extra_headers_encrypted)
            if protocol is not None and protocol.extra_headers_encrypted is not None
            else None
        ),
    )


def _store_balance(provider: Provider, result: BalanceResult, now: datetime) -> None:
    provider.balance_amount = result.amount
    provider.balance_currency = result.currency
    provider.balance_used = result.used
    provider.balance_is_available = result.is_available
    provider.balance_error = None
    provider.last_balance_sync_at = now
    provider.balance_updated_at = now


def load_balance_config(provider: Provider, settings: Settings) -> BalanceQueryConfig:
    encrypted = provider.balance_query_config_encrypted
    if encrypted is None:
        return BalanceQueryConfig()
    try:
        values = orjson.loads(decrypt_secret(encrypted, settings=settings))
        if not isinstance(values, dict):
            raise BalanceConfigError("Stored balance configuration must be a JSON object")
        return BalanceQueryConfig.from_mapping(values)
    except Exception:
        logger.warning(
            "Stored balance configuration for provider_id=%s could not be decoded",
            provider.id,
        )
        return BalanceQueryConfig()


def balance_response(provider: Provider, settings: Settings) -> ProviderBalanceResponse:
    config = load_balance_config(provider, settings)
    return ProviderBalanceResponse(
        query_type=provider.balance_query_type,
        auto_sync=provider.balance_auto_sync,
        sync_interval_seconds=provider.balance_sync_interval_seconds,
        config=ProviderBalanceConfigResponse(
            base_url=config.base_url,
            has_api_key=bool(config.api_key),
            user_id=config.user_id,
            has_headers=bool(config.headers),
            path=config.path,
            method=config.method,
            amount_path=config.amount_path,
            used_path=config.used_path,
            available_path=config.available_path,
            currency=config.currency,
            divisor=config.divisor,
        ),
        amount=provider.balance_amount,
        currency=provider.balance_currency,
        used=provider.balance_used,
        is_available=provider.balance_is_available,
        updated_at=provider.balance_updated_at,
        last_sync_at=provider.last_balance_sync_at,
        error=provider.balance_error,
    )


def stored_balance_mapping(provider: Provider, settings: Settings) -> dict[str, object]:
    return load_balance_config(provider, settings).to_mapping()


def merge_balance_config(
    existing: Mapping[str, object],
    payload: ProviderBalanceConfigInput,
) -> dict[str, object]:
    """Overlay explicitly submitted fields on the stored configuration."""

    merged: dict[str, object] = dict(existing)
    for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def balance_config_from_mapping(values: Mapping[str, object]) -> BalanceQueryConfig:
    return BalanceQueryConfig.from_mapping(values)


def balance_config_mapping(payload: ProviderBalanceConfigInput) -> dict[str, object]:
    return balance_config_from_mapping(
        payload.model_dump(exclude_unset=True, mode="json")
    ).to_mapping()


def validate_balance_mapping(
    query_type: BalanceQueryType | None,
    values: Mapping[str, object],
) -> None:
    if query_type is None:
        if values:
            raise BalanceConfigError("Balance configuration requires an upstream type")
        return
    validate_balance_config(query_type, balance_config_from_mapping(values))


def encrypt_balance_mapping(values: Mapping[str, object], settings: Settings) -> bytes | None:
    if not values:
        return None
    canonical = orjson.dumps(values, option=orjson.OPT_SORT_KEYS).decode()
    return encrypt_secret(canonical, settings=settings)


def raise_invalid_balance_config(exc: Exception) -> NoReturn:
    raise_auth_error(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_balance_config",
        sanitize_log_event(exc),
    )


def _balance_error_message(
    exc: BaseException,
    *,
    query_type: BalanceQueryType | None = None,
) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        status_label = f"{response.status_code} {response.reason_phrase}".strip()
        message = f"Upstream provider returned {status_label}"
        detail = _upstream_error_detail(response)
        if detail:
            message = f"{message}: {detail}"
        hint = _balance_auth_hint(response.status_code, query_type)
        if hint:
            message = f"{message}. {hint}"
    else:
        detail = sanitize_log_event(exc).strip()
        message = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
    if len(message) <= _MAX_UPSTREAM_ERROR_CHARS:
        return message
    return f"{message[: _MAX_UPSTREAM_ERROR_CHARS - 1]}…"


def _balance_auth_hint(status_code: int, query_type: BalanceQueryType | None) -> str | None:
    """Explain the upstream authentication model behind a rejected balance request."""

    if status_code not in (401, 403) or query_type is not BalanceQueryType.NEW_API:
        return None
    return (
        "new-api / one-api only accepts a user access token on /api/user/self, not the sk- "
        "relay key: set the balance query API key override to a token generated in the "
        "upstream console personal settings, and fill the new-api user id only when the "
        "deployment requires the New-Api-User header"
    )


def _balance_detection_message(failures: Mapping[BalanceQueryType, BaseException]) -> str:
    message = "No supported upstream balance API responded to the detection probes"
    reasons = [
        f"{query_type.value}: {_balance_error_message(exc, query_type=query_type)}"
        for query_type, exc in failures.items()
    ]
    if not reasons:
        return message
    return truncate_balance_error(f"{message} ({'; '.join(reasons)})")


def _upstream_error_detail(response: httpx.Response) -> str:
    try:
        detail = orjson.dumps(redact_json(response.json())).decode()
    except ValueError:
        detail = response.text.strip()
    return sanitize_log_event(detail)
