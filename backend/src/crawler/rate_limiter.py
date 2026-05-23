"""
Token bucket rate limiter — per-host request throttling.

Implements a distributed token bucket using Redis. Each host gets its own
bucket that refills at a configured rate. Workers must acquire a token
before fetching from a host, ensuring we don't overwhelm documentation sites.

Why token bucket?
- Allows short bursts while enforcing average rate
- Trivial to implement in Redis with atomic operations
- Standard approach used by AWS, Cloudflare, etc.
"""

import time

import redis.asyncio as aioredis


class RateLimiter:
    """
    Distributed token bucket rate limiter using Redis.

    Each host has a bucket with:
    - tokens: current available tokens
    - max_tokens: maximum capacity (burst size)
    - refill_rate: tokens added per second
    - last_refill: timestamp of last token refill
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def try_acquire(
        self,
        hostname: str,
        max_tokens: int = 5,
        refill_rate: float = 1.0,
    ) -> bool:
        """
        Try to acquire a token for the given host.

        Args:
            hostname: The host to rate limit.
            max_tokens: Maximum burst size.
            refill_rate: Tokens per second to refill.

        Returns:
            True if a token was acquired, False if rate limited.
        """
        key = f"ratelimit:{hostname}"
        now = time.time()

        # Lua script for atomic token bucket operation.
        # This runs atomically on the Redis server — no race conditions.
        lua_script = """
        local key = KEYS[1]
        local max_tokens = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket[1])
        local last_refill = tonumber(bucket[2])

        -- Initialize bucket if it doesn't exist
        if tokens == nil then
            tokens = max_tokens
            last_refill = now
        end

        -- Refill tokens based on elapsed time
        local elapsed = now - last_refill
        local new_tokens = elapsed * refill_rate
        tokens = math.min(max_tokens, tokens + new_tokens)

        -- Try to consume one token
        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 3600)
            return 1
        else
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 3600)
            return 0
        end
        """

        result = await self._redis.eval(
            lua_script, 1, key, str(max_tokens), str(refill_rate), str(now)
        )
        return bool(result)

    async def wait_for_token(
        self,
        hostname: str,
        max_tokens: int = 5,
        refill_rate: float = 1.0,
        max_wait: float = 30.0,
    ) -> bool:
        """
        Wait until a token is available, with a maximum wait time.

        Uses exponential backoff to avoid busy-waiting on Redis.

        Returns:
            True if token was acquired within max_wait, False if timed out.
        """
        import asyncio

        start = time.time()
        wait = 0.1  # Start with 100ms backoff

        while time.time() - start < max_wait:
            if await self.try_acquire(hostname, max_tokens, refill_rate):
                return True
            await asyncio.sleep(wait)
            wait = min(wait * 1.5, 2.0)  # Cap at 2s between retries

        return False
