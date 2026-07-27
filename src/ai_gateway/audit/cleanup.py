from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_gateway.core.config import Settings
from ai_gateway.db.models import RequestLogDetail

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AuditLogCleanupScheduler:
    """定期清理过期的审计日志详情记录"""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        clock: Clock = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._clock = clock
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        """主循环：定期执行清理"""
        interval = self._settings.audit_log_cleanup_interval_seconds
        while not self._stopped.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled audit log cleanup iteration failed")
            try:
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=interval,
                )
            except TimeoutError:
                pass

    def stop(self) -> None:
        """停止调度器"""
        self._stopped.set()

    async def run_once(self) -> None:
        """执行一次清理"""
        retention_days = self._settings.audit_log_retention_days
        if retention_days == 0:
            logger.debug("Audit log cleanup is disabled (retention_days=0)")
            return

        cutoff = self._clock() - timedelta(days=retention_days)

        async with self._session_factory() as session:
            result = await session.execute(
                delete(RequestLogDetail).where(RequestLogDetail.created_at < cutoff)
            )
            await session.commit()
            deleted_count = int(getattr(result, "rowcount", 0))

        if deleted_count > 0:
            logger.info(
                "Cleaned up %d expired audit log details (retention: %d days)",
                deleted_count,
                retention_days,
            )
