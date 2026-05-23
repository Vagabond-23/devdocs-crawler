"""
Content deduplicator using SHA-256 (exact) and SimHash (near-duplicate).

Multi-level deduplication prevents indexing the same content multiple times
(e.g., pages served at different URLs, or pages with minor template variations).

SHA-256: Exact byte-for-byte duplicate detection.
SimHash: Locality-sensitive hash that produces similar hashes for similar text.
         Two documents are near-duplicates if Hamming distance ≤ 3 out of 64 bits.
"""

import hashlib
import re
from collections import Counter

import redis.asyncio as aioredis


def compute_sha256(content: str) -> str:
    """Compute SHA-256 hash of text content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _tokenize(text: str) -> list[str]:
    """Tokenize text into words for SimHash computation."""
    # Lowercase and extract word tokens
    text = text.lower()
    return re.findall(r"\w+", text)


def _hash_token(token: str) -> int:
    """Hash a single token to a 64-bit integer."""
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(h[:16], 16)  # Use first 64 bits


def compute_simhash(content: str) -> int:
    """
    Compute a 64-bit SimHash of text content.

    Algorithm:
    1. Tokenize text into words
    2. Hash each token to a 64-bit value
    3. For each bit position, sum +1 if the token's bit is 1, -1 if 0
    4. Final hash: bit i = 1 if sum[i] > 0, else 0

    SimHash preserves locality: similar documents produce similar hashes.
    """
    tokens = _tokenize(content)
    if not tokens:
        return 0

    # Weight tokens by frequency
    token_counts = Counter(tokens)

    # Initialize bit sums
    bit_sums = [0] * 64

    for token, weight in token_counts.items():
        token_hash = _hash_token(token)
        for i in range(64):
            if token_hash & (1 << i):
                bit_sums[i] += weight
            else:
                bit_sums[i] -= weight

    # Build final hash
    simhash = 0
    for i in range(64):
        if bit_sums[i] > 0:
            simhash |= (1 << i)

    return simhash


def hamming_distance(hash1: int, hash2: int) -> int:
    """Compute the Hamming distance between two 64-bit hashes."""
    xor = hash1 ^ hash2
    return bin(xor).count("1")


class Deduplicator:
    """
    Multi-level content deduplicator with Redis-backed storage.

    Level 1: SHA-256 exact match (stored in Redis Set)
    Level 2: SimHash near-duplicate (stored in Redis Sorted Set)
    """

    # Near-duplicate threshold: documents with Hamming distance ≤ 3 are dupes.
    SIMHASH_THRESHOLD = 3

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def is_duplicate(self, content: str) -> tuple[bool, str, int]:
        """
        Check if content is a duplicate (exact or near).

        Returns:
            (is_duplicate, sha256_hash, simhash_value)
        """
        sha256 = compute_sha256(content)
        simhash = compute_simhash(content)

        # Level 1: Exact duplicate check
        if await self._redis.sismember("fingerprints:sha256", sha256):
            return (True, sha256, simhash)

        # Level 2: Near-duplicate check
        # Compare against stored simhashes.
        # For production scale, you'd use a more efficient structure (e.g., bit sampling).
        # For our doc corpus size (<50k pages), linear scan is acceptable.
        stored_hashes = await self._redis.smembers("fingerprints:simhash")
        for stored in stored_hashes:
            stored_int = int(stored)
            if hamming_distance(simhash, stored_int) <= self.SIMHASH_THRESHOLD:
                return (True, sha256, simhash)

        return (False, sha256, simhash)

    async def register(self, sha256: str, simhash: int) -> None:
        """Register a content fingerprint after successful indexing."""
        pipe = self._redis.pipeline()
        pipe.sadd("fingerprints:sha256", sha256)
        pipe.sadd("fingerprints:simhash", str(simhash))
        await pipe.execute()
