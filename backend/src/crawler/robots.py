"""
Robots.txt manager with caching.

Fetches, parses, and caches robots.txt for each host. Uses the `protego`
library for RFC-compliant parsing. Cache entries have a configurable TTL
to handle robots.txt updates without re-fetching on every request.
"""

import time
import logging

import httpx
from protego import Protego
import redis.asyncio as aioredis

from src.config import settings

logger = logging.getLogger(__name__)

# Cache TTL: how long to keep robots.txt before re-fetching (1 hour).
ROBOTS_CACHE_TTL = 3600


class RobotsManager:
    """
    Manages robots.txt fetching, parsing, and caching via Redis.

    Uses Redis to share robots state across multiple crawler workers.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._http = httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": settings.crawler_user_agent},
            follow_redirects=True,
        )

    async def is_allowed(self, url: str, hostname: str) -> bool:
        """
        Check if a URL is allowed by the host's robots.txt.

        Fetches and caches robots.txt if not already cached or if cache is stale.
        """
        robots_txt = await self._get_robots(hostname)
        if robots_txt is None:
            # No robots.txt found — assume everything is allowed.
            return True

        try:
            rp = Protego.parse(robots_txt)
            return rp.can_fetch(url, settings.crawler_user_agent)
        except Exception:
            logger.warning(f"Failed to parse robots.txt for {hostname}, allowing URL")
            return True

    async def get_crawl_delay(self, hostname: str) -> float | None:
        """
        Get the Crawl-delay directive for our user agent, if any.

        Returns delay in seconds, or None if not specified.
        """
        robots_txt = await self._get_robots(hostname)
        if robots_txt is None:
            return None

        try:
            rp = Protego.parse(robots_txt)
            delay = rp.crawl_delay(settings.crawler_user_agent)
            return float(delay) if delay is not None else None
        except Exception:
            return None

    async def _get_robots(self, hostname: str) -> str | None:
        """
        Get robots.txt content from cache or fetch from the host.

        Cache structure in Redis:
            robots:{hostname} → Hash { content: str, fetched_at: float }
        """
        cache_key = f"robots:{hostname}"

        # Check cache
        cached = await self._redis.hgetall(cache_key)
        if cached:
            fetched_at = float(cached.get("fetched_at", 0))
            if time.time() - fetched_at < ROBOTS_CACHE_TTL:
                content = cached.get("content", "")
                return content if content != "__NONE__" else None

        # Fetch robots.txt
        robots_url = f"https://{hostname}/robots.txt"
        try:
            response = await self._http.get(robots_url)
            if response.status_code == 200:
                content = response.text
            else:
                content = None
        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt for {hostname}: {e}")
            content = None

        # Cache the result (including negative results to avoid re-fetching)
        await self._redis.hset(
            cache_key,
            mapping={
                "content": content if content is not None else "__NONE__",
                "fetched_at": str(time.time()),
            },
        )
        await self._redis.expire(cache_key, ROBOTS_CACHE_TTL)

        return content

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()
