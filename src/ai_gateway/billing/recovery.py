from __future__ import annotations

import asyncio
import logging

from ai_gateway.billing.service import BillingService

logger = logging.getLogger(__name__)


class BillingRecoveryScheduler:
    def __init__(
        self,
        billing: BillingService,
        *,
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._billing = billing
        self._interval_seconds = interval_seconds
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self._billing.recover_orphaned_reservations()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("WebSocket billing recovery iteration failed")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()
