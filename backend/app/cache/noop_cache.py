"""
No-op in-memory cache — replaces Redis.

All read/write operations are no-ops that preserve the same interface used
by the similarity and forecast endpoints so that no endpoint code needs to
change beyond dropping the import of RedisClient.
"""

from typing import Optional


class NoopCache:
    """Thin cache stub — never stores anything, always misses."""

    async def get(self, key: str) -> Optional[str]:  # noqa: ARG002
        return None

    async def set(self, key: str, value: str, ttl: int = 86_400) -> None:  # noqa: ARG002
        pass

    async def delete(self, key: str) -> None:  # noqa: ARG002
        pass

    async def invalidate_pattern(self, pattern: str) -> int:  # noqa: ARG002
        return 0


# Module-level singleton — safe to import anywhere
_instance = NoopCache()


async def get_noop_cache() -> NoopCache:
    """FastAPI dependency — always returns the singleton noop cache."""
    return _instance
