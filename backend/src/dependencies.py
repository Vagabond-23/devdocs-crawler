"""
Dependency injection for the FastAPI application.

Centralizes shared resources (Redis, Meilisearch client) so they can be
injected into route handlers and services via FastAPI's Depends().
"""

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from meilisearch_python_sdk import AsyncClient as MeiliClient

from src.config import settings

# ── Redis ────────────────────────────────────────────────────
_redis_pool: aioredis.Redis | None = None


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Yield a Redis connection from the pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
    yield _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool on shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None


# ── Meilisearch ──────────────────────────────────────────────
_meili_client: MeiliClient | None = None


async def get_meili() -> AsyncGenerator[MeiliClient, None]:
    """Yield a Meilisearch async client."""
    global _meili_client
    if _meili_client is None:
        _meili_client = MeiliClient(settings.meili_url, settings.meili_master_key)
    yield _meili_client


async def close_meili() -> None:
    """Close the Meilisearch client on shutdown."""
    global _meili_client
    if _meili_client is not None:
        await _meili_client.aclose()
        _meili_client = None
