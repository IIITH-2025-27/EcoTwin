from typing import Optional

import redis.asyncio as aioredis
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_pool: Optional[aioredis.Redis] = None


class RedisClient:
    """Thin async Redis wrapper with transparent error handling."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def get(self, key: str) -> Optional[str]:
        try:
            value = await self._client.get(key)
            return value.decode("utf-8") if value else None
        except Exception as exc:
            logger.warning("Redis GET failed", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: str, ttl: int = settings.REDIS_TTL) -> None:
        try:
            await self._client.setex(key, ttl, value)
        except Exception as exc:
            logger.warning("Redis SET failed", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception as exc:
            logger.warning("Redis DEL failed", key=key, error=str(exc))

    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns number of keys deleted."""
        try:
            keys = await self._client.keys(pattern)
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception as exc:
            logger.warning("Redis pattern invalidation failed", pattern=pattern, error=str(exc))
            return 0


async def _get_pool() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _pool


async def get_redis_client() -> Optional[RedisClient]:
    """FastAPI dependency – returns None if Redis is unreachable (graceful degradation)."""
    try:
        pool = await _get_pool()
        return RedisClient(pool)
    except Exception as exc:
        logger.error("Failed to connect to Redis", error=str(exc))
        return None
