"""
redis_client.py — Redis removed.

All callers that imported RedisClient / get_redis_client still work because
we re-export the NoopCache under the same names.
"""

from app.cache.noop_cache import NoopCache as RedisClient  # noqa: F401
from app.cache.noop_cache import get_noop_cache as get_redis_client  # noqa: F401

__all__ = ["RedisClient", "get_redis_client"]
