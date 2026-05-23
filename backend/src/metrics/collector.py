"""
Metrics collector — Redis-backed real-time metrics.

Centralizes metric updates from crawler workers. All metrics are stored
as Redis keys for fast, lock-free concurrent updates.
"""

import redis.asyncio as aioredis


class MetricsCollector:
    """
    Collects and exposes crawler metrics via Redis.

    All counters use Redis INCR for atomic, lock-free updates
    that work correctly across multiple concurrent workers.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def increment(self, metric: str, amount: int = 1) -> None:
        """Increment a counter metric."""
        await self._redis.incrby(f"metrics:{metric}", amount)

    async def set_gauge(self, metric: str, value: int) -> None:
        """Set a gauge metric to an absolute value."""
        await self._redis.set(f"metrics:{metric}", value)

    async def get(self, metric: str) -> int:
        """Get the current value of a metric."""
        val = await self._redis.get(f"metrics:{metric}")
        return int(val) if val else 0

    async def get_all(self) -> dict[str, int]:
        """Get all metrics as a dictionary."""
        keys = [
            "metrics:pages_fetched",
            "metrics:pages_failed",
            "metrics:pages_304",
            "metrics:pages_duplicate",
            "metrics:pages_indexed",
            "metrics:active_workers",
        ]
        pipe = self._redis.pipeline()
        for key in keys:
            pipe.get(key)
        values = await pipe.execute()

        return {
            key.replace("metrics:", ""): int(val or 0)
            for key, val in zip(keys, values)
        }

    async def reset(self) -> None:
        """Reset all metrics. For testing only."""
        keys = await self._redis.keys("metrics:*")
        if keys:
            await self._redis.delete(*keys)
