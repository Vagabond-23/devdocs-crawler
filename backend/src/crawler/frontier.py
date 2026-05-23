"""
Redis-backed URL frontier.

The frontier is the central queue of URLs to be crawled. This implementation
uses Redis for distributed access across multiple workers.

Architecture:
- Per-host queues (Redis Lists) for host-aware scheduling
- A global host set to track which hosts have pending URLs
- A seen-URL set for O(1) URL deduplication
"""

import logging

import redis.asyncio as aioredis

from src.crawler.url_normalizer import extract_hostname

logger = logging.getLogger(__name__)


class Frontier:
    """
    Redis-backed crawl frontier with per-host queues.

    Keys used:
        frontier:host:{hostname}  — List of URLs for a specific host
        frontier:hosts            — Set of hostnames with pending URLs
        seen_urls                 — Set of all URLs ever discovered (dedup)
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def enqueue(self, url: str, hostname: str | None = None) -> bool:
        """
        Add a URL to the frontier if it hasn't been seen before.

        Args:
            url: Normalized URL to enqueue.
            hostname: Pre-extracted hostname (avoids re-parsing).

        Returns:
            True if the URL was enqueued, False if it was already seen.
        """
        if hostname is None:
            hostname = extract_hostname(url)
        if hostname is None:
            return False

        # Atomic URL deduplication — SADD returns 1 if the member was added.
        was_new = await self._redis.sadd("seen_urls", url)
        if not was_new:
            return False

        # Push URL to the host's queue and register the host.
        pipe = self._redis.pipeline()
        pipe.rpush(f"frontier:host:{hostname}", url)
        pipe.sadd("frontier:hosts", hostname)
        await pipe.execute()

        logger.debug(f"Enqueued: {url} → {hostname}")
        return True

    async def dequeue(self, hostname: str) -> str | None:
        """
        Pop the next URL from a host's queue.

        Returns None if the queue is empty. Also removes the host from
        the active set if its queue becomes empty.
        """
        url = await self._redis.lpop(f"frontier:host:{hostname}")

        if url is None:
            # Queue is empty — remove host from active set.
            await self._redis.srem("frontier:hosts", hostname)

        return url

    async def get_active_hosts(self) -> list[str]:
        """Get all hosts that have URLs waiting to be crawled."""
        hosts = await self._redis.smembers("frontier:hosts")
        return list(hosts)

    async def get_queue_depth(self, hostname: str) -> int:
        """Get the number of URLs waiting in a host's queue."""
        return await self._redis.llen(f"frontier:host:{hostname}")

    async def get_total_queue_depth(self) -> int:
        """Get total URLs waiting across all hosts."""
        hosts = await self.get_active_hosts()
        if not hosts:
            return 0
        pipe = self._redis.pipeline()
        for host in hosts:
            pipe.llen(f"frontier:host:{host}")
        depths = await pipe.execute()
        return sum(depths)

    async def get_seen_count(self) -> int:
        """Get the total number of unique URLs discovered."""
        return await self._redis.scard("seen_urls")

    async def is_seen(self, url: str) -> bool:
        """Check if a URL has already been discovered."""
        return bool(await self._redis.sismember("seen_urls", url))

    async def clear(self) -> None:
        """Clear all frontier state. Use with caution — for testing/reset only."""
        hosts = await self.get_active_hosts()
        pipe = self._redis.pipeline()
        for host in hosts:
            pipe.delete(f"frontier:host:{host}")
        pipe.delete("frontier:hosts")
        pipe.delete("seen_urls")
        await pipe.execute()
        logger.info("Frontier cleared")
