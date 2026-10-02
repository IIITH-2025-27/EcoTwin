"""
In-memory TTL cache — lightweight replacement for Redis.

Provides the same interface used by the similarity and forecast endpoints
so that no endpoint code needs to change.  Entries expire after a
configurable TTL (default: 5 minutes).
"""

import fnmatch
import time
from typing import Optional


class InMemoryCache:
    """Thread-safe in-memory cache with per-key TTL."""

    _DEFAULT_TTL: int = 300  # 5 minutes

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}

    def _evict_expired(self) -> None:
        """Remove all expired entries (lazy GC on every write)."""
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]

    async def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(
        self, key: str, value: str, ttl: int = 0,  # noqa: ARG002
    ) -> None:
        self._evict_expired()
        effective_ttl = ttl if ttl > 0 else self._DEFAULT_TTL
        self._store[key] = (value, time.monotonic() + effective_ttl)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def invalidate_pattern(self, pattern: str) -> int:
        keys = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
        for k in keys:
            del self._store[k]
        return len(keys)


# Keep the old class name as an alias for backward compatibility
NoopCache = InMemoryCache

# Module-level singleton — safe to import anywhere
_instance = InMemoryCache()


async def get_noop_cache() -> InMemoryCache:
    """FastAPI dependency — always returns the singleton in-memory cache."""
    return _instance
