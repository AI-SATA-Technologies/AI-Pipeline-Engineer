"""LMS delivery via a transactional outbox.

Attendance is written to ``attendance_events`` first (status 'pending'); this
module's background loop then POSTs each pending event to LMS_API_URL and marks
it 'sent'. Failures (network errors, timeouts, non-2xx replies) are retried with
exponential backoff and survive restarts; after LMS_MAX_ATTEMPTS an event is
marked 'failed' (visible via GET /api/attendance) instead of being lost.
"""
import asyncio
import logging
from datetime import UTC

import httpx

import database
from config import LMS_API_TOKEN, LMS_API_URL, LMS_MAX_ATTEMPTS, LMS_TIMEOUT

logger = logging.getLogger('attendance.lms')

_BASE_DELAY = 5.0      # seconds before the first retry
_MAX_DELAY = 600.0     # cap between retries
_IDLE_POLL = 30.0      # wake up at least this often to pick up due retries


def enabled() -> bool:
    return bool(LMS_API_URL)


def retry_delay(attempts: int) -> float:
    """Backoff after `attempts` failed deliveries: 5 s, 10 s, 20 s … capped at 10 min."""
    return min(_BASE_DELAY * 2 ** max(attempts - 1, 0), _MAX_DELAY)


class LmsOutbox:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._owns_client = client is None
        self._wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self._client is None:
            headers = {'Authorization': f'Bearer {LMS_API_TOKEN}'} if LMS_API_TOKEN else {}
            self._client = httpx.AsyncClient(timeout=LMS_TIMEOUT, headers=headers)
        self._task = asyncio.create_task(self._run(), name='lms-outbox')

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client and self._owns_client:
            await self._client.aclose()

    def wake(self) -> None:
        """Signal that new events are pending. Safe to call from any thread."""
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._wake.set)

    async def _run(self) -> None:
        while True:
            try:
                sent_full_batch = await self.drain_once()
            except database.StorageError as exc:
                logger.warning('outbox: database unavailable (%s); retrying', exc)
                sent_full_batch = False
            except Exception:  # never let the loop die
                logger.exception('outbox: unexpected error')
                sent_full_batch = False
            if sent_full_batch:
                continue  # more may be due right now
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=_IDLE_POLL)
            except TimeoutError:
                pass

    async def drain_once(self, batch: int = 50) -> bool:
        """Deliver due events once. Returns True if a full batch was processed."""
        rows = await asyncio.to_thread(database.fetch_due_events, batch)
        for event_id, reg, detected_at, attempts in rows:
            await self._deliver(event_id, reg, detected_at, attempts)
        return len(rows) == batch

    async def _deliver(self, event_id: int, reg: str, detected_at, attempts: int) -> None:
        payload = {
            'registration_number': reg,
            # Always UTC (the DB hands back its session timezone), as in v3.1.
            'detected_at': detected_at.astimezone(UTC).isoformat(timespec='seconds'),
        }
        attempts += 1
        try:
            resp = await self._client.post(LMS_API_URL, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            give_up = attempts >= LMS_MAX_ATTEMPTS
            delay = retry_delay(attempts)
            await asyncio.to_thread(
                database.mark_event_retry, event_id, attempts, _describe(exc), delay, give_up
            )
            if give_up:
                logger.error('LMS delivery FAILED permanently for %s after %d attempts: %s',
                             reg, attempts, _describe(exc))
            else:
                logger.warning('LMS delivery failed for %s (attempt %d), retry in %.0fs: %s',
                               reg, attempts, delay, _describe(exc))
            return
        await asyncio.to_thread(database.mark_event_sent, event_id, attempts)
        logger.info('LMS notified: %s', reg)


def _describe(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f'HTTP {exc.response.status_code}'
    return f'{type(exc).__name__}: {exc}'.strip()
