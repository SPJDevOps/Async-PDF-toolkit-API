"""In-process concurrency and rate-limit state (single-replica demos)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from app.config import get_settings

_job_semaphore: asyncio.Semaphore | None = None
_rate_hits: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = asyncio.Lock()


def get_job_semaphore() -> asyncio.Semaphore:
    global _job_semaphore
    if _job_semaphore is None:
        _job_semaphore = asyncio.Semaphore(get_settings().max_concurrent_jobs)
    return _job_semaphore


def reset_limit_state() -> None:
    """Reset process-local limit state (for tests)."""
    global _job_semaphore
    _job_semaphore = None
    _rate_hits.clear()


async def acquire_job_slot() -> None:
    await get_job_semaphore().acquire()


def release_job_slot() -> None:
    get_job_semaphore().release()


async def check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    limit = get_settings().rate_limit_per_minute
    now = time.monotonic()
    window = 60.0
    async with _rate_lock:
        hits = _rate_hits[client_ip]
        while hits and now - hits[0] >= window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True
