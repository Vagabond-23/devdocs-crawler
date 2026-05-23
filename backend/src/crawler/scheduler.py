"""
Host-aware scheduler — fair scheduling across domains.

Implements round-robin scheduling across hosts to prevent any single
fast domain from monopolizing crawler workers. Respects per-host
rate limits and concurrency caps.

This is the key distributed systems component that differentiates this
crawler from a naive "fetch everything as fast as possible" approach.
"""

import asyncio
import logging
from dataclasses import dataclass

import redis.asyncio as aioredis

from src.crawler.frontier import Frontier
from src.crawler.rate_limiter import RateLimiter
from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ScheduledURL:
    """A URL that has been approved for fetching by the scheduler."""

    url: str
    hostname: str


class Scheduler:
    """
    Host-aware round-robin scheduler.

    Algorithm:
    1. Get list of hosts with non-empty queues
    2. Round-robin across hosts
    3. For each host:
       a. Check rate limiter
       b. Check active worker count < host concurrency limit
       c. If allowed → pop URL and return it
       d. If throttled → skip to next host
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        frontier: Frontier,
        rate_limiter: RateLimiter,
    ) -> None:
        self._redis = redis
        self._frontier = frontier
        self._rate_limiter = rate_limiter
        self._host_index = 0  # Round-robin pointer

    async def next_url(self) -> ScheduledURL | None:
        """
        Get the next URL to crawl, respecting fairness and rate limits.

        Returns None if no URLs are available or all hosts are rate-limited.
        """
        hosts = await self._frontier.get_active_hosts()
        if not hosts:
            return None

        # Sort for deterministic round-robin
        hosts = sorted(hosts)
        num_hosts = len(hosts)

        # Try each host starting from our round-robin pointer
        for i in range(num_hosts):
            idx = (self._host_index + i) % num_hosts
            hostname = hosts[idx]

            # Check rate limit
            refill_rate = 1000.0 / settings.crawler_default_delay_ms
            if not await self._rate_limiter.try_acquire(
                hostname, max_tokens=3, refill_rate=refill_rate
            ):
                continue

            # Check per-host concurrency limit
            active = await self._get_active_workers(hostname)
            if active >= 2:  # Per-host concurrency limit
                continue

            # Dequeue URL
            url = await self._frontier.dequeue(hostname)
            if url is None:
                continue

            # Advance round-robin pointer
            self._host_index = (idx + 1) % num_hosts

            return ScheduledURL(url=url, hostname=hostname)

        return None

    async def _get_active_workers(self, hostname: str) -> int:
        """Get the number of active workers for a host."""
        count = await self._redis.get(f"workers:active:{hostname}")
        return int(count) if count else 0

    async def register_worker(self, hostname: str) -> None:
        """Register a worker as actively fetching from a host."""
        pipe = self._redis.pipeline()
        pipe.incr(f"workers:active:{hostname}")
        pipe.incr("metrics:active_workers")
        await pipe.execute()

    async def release_worker(self, hostname: str) -> None:
        """Release a worker after it finishes fetching."""
        pipe = self._redis.pipeline()
        pipe.decr(f"workers:active:{hostname}")
        pipe.decr("metrics:active_workers")
        await pipe.execute()

        # Ensure we don't go below 0
        count = await self._redis.get(f"workers:active:{hostname}")
        if count and int(count) < 0:
            await self._redis.set(f"workers:active:{hostname}", 0)
