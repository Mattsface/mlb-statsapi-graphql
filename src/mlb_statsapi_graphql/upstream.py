"""Admission and request-local observations around logical library lookups."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from time import monotonic
from uuid import uuid4

logger = logging.getLogger(__name__)


def _log(event: str, **fields: object) -> None:
    record = {"event": event, **fields}
    # JSON keeps fields useful with plain text handlers; extra also supports
    # applications that install their own structured logging formatter.
    logger.info(json.dumps(record), extra=record)


@dataclass
class RequestStats:
    lookup_count: int = 0
    error_count: int = 0
    cancellation_count: int = 0
    queue_wait_seconds: float = 0.0
    lookup_seconds: float = 0.0


class RequestLookups:
    def __init__(self, semaphore: asyncio.Semaphore) -> None:
        self.semaphore = semaphore
        self.request_id = uuid4().hex
        self.stats = RequestStats()
        self._tasks: set[asyncio.Task] = set()
        self._closed = False

    async def run[V](self, kind: str, fetch: Callable[[], Awaitable[V]]) -> V:
        if self._closed:
            raise asyncio.CancelledError
        task = asyncio.current_task()
        assert task is not None
        self._tasks.add(task)
        queued_at = monotonic()
        started_at = None
        outcome = "cancelled"
        try:
            # Release on success, failure, or cancellation. Hold the permit
            # through the library's retries, backoff, and response parsing.
            async with self.semaphore:
                started_at = monotonic()
                self.stats.lookup_count += 1
                try:
                    result = await fetch()
                except Exception:
                    outcome = "error"
                    self.stats.error_count += 1
                    raise
                outcome = "success"
                return result
        finally:
            self._tasks.discard(task)
            finished_at = monotonic()
            queue_wait = (finished_at if started_at is None else started_at) - queued_at
            duration = 0.0 if started_at is None else finished_at - started_at
            self.stats.queue_wait_seconds += queue_wait
            self.stats.lookup_seconds += duration
            if outcome == "cancelled":
                self.stats.cancellation_count += 1
            _log(
                "mlb_upstream_lookup", request_id=self.request_id,
                lookup_kind=kind, admitted=started_at is not None,
                outcome=outcome, queue_wait_seconds=queue_wait,
                lookup_seconds=duration,
            )

    async def aclose(self) -> None:
        """Stop detached DataLoader lookups before logging the final totals."""
        self._closed = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def log_summary(self) -> None:
        _log("mlb_graphql_request", request_id=self.request_id, **asdict(self.stats))
