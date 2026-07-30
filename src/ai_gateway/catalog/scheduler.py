from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_gateway.admin.model_sync import HttpClientProvider, sync_provider_models
from ai_gateway.core.config import Settings
from ai_gateway.db.models import Provider

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
SyncProvider = Callable[..., Awaitable[object]]


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ModelSyncScheduler:
    def __init__(
        self,
        *,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        http_client_factory: HttpClientProvider,
        settings: Settings,
        sync_provider: SyncProvider = sync_provider_models,
        clock: Clock = _utcnow,
        wake_interval_seconds: float = 60.0,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._http_client_factory = http_client_factory
        self._settings = settings
        self._sync_provider = sync_provider
        self._clock = clock
        self._wake_interval_seconds = wake_interval_seconds
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled model discovery iteration failed")
            try:
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=self._wake_interval_seconds,
                )
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()

    async def run_once(self) -> None:
        now = self._clock()
        async with self._session_factory() as session:
            providers = list(
                await session.scalars(
                    select(Provider).where(
                        Provider.enabled.is_(True),
                        Provider.auto_load_models.is_(True),
                    )
                )
            )
        due_provider_ids = [
            provider.id for provider in providers if _provider_is_due(provider, now)
        ]
        for provider_id in due_provider_ids:
            await self._sync_if_locked(provider_id)

    async def _sync_if_locked(self, provider_id: int) -> None:
        lock_name = f"model-sync:{provider_id}"
        async with self._engine.connect() as lock_connection:
            acquired = await lock_connection.scalar(select(func.get_lock(lock_name, 0)))
            if acquired != 1:
                return
            try:
                async with self._session_factory() as session:
                    provider = await session.get(Provider, provider_id)
                    if provider is None or not _provider_is_due(provider, self._clock()):
                        return
                    await self._sync_provider(
                        provider_id,
                        session=session,
                        http_client_factory=self._http_client_factory,
                        settings=self._settings,
                        clock=self._clock,
                        release_connection_before_discovery=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Scheduled model discovery failed for provider_id=%s",
                    provider_id,
                )
            finally:
                await asyncio.shield(lock_connection.execute(select(func.release_lock(lock_name))))


def _provider_is_due(provider: Provider, now: datetime) -> bool:
    if not provider.enabled or not provider.auto_load_models:
        return False
    if provider.last_model_sync_at is None:
        return True
    return (
        provider.last_model_sync_at + timedelta(seconds=provider.model_sync_interval_seconds) <= now
    )
