"""
Seed script — populates the frontier with initial documentation URLs.

Usage:
    python -m scripts.seed
"""

import asyncio
import redis.asyncio as aioredis

SEED_URLS = [
    "https://docs.python.org/3/",
    "https://docs.python.org/3/library/",
    "https://docs.python.org/3/tutorial/",
    "https://developer.mozilla.org/en-US/docs/Web",
    "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
    "https://developer.mozilla.org/en-US/docs/Web/HTML",
    "https://developer.mozilla.org/en-US/docs/Web/CSS",
    "https://fastapi.tiangolo.com/",
    "https://fastapi.tiangolo.com/tutorial/",
    "https://kubernetes.io/docs/",
    "https://kubernetes.io/docs/concepts/",
]


async def main():
    redis = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)

    from src.crawler.frontier import Frontier
    from src.crawler.url_normalizer import normalize_url, extract_hostname

    frontier = Frontier(redis)

    print("Seeding frontier with documentation URLs...")
    for url in SEED_URLS:
        normalized = normalize_url(url)
        if normalized:
            hostname = extract_hostname(normalized)
            if hostname:
                added = await frontier.enqueue(normalized, hostname)
                status = "✓ added" if added else "– skipped (already seen)"
                print(f"  {status}: {normalized}")

    total = await frontier.get_seen_count()
    print(f"\nTotal URLs in frontier: {total}")
    await redis.close()


if __name__ == "__main__":
    asyncio.run(main())
