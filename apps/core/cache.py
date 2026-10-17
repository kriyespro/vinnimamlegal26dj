"""Redis cache that degrades instead of taking the site down when Redis is unreachable."""
import functools
import logging

from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def _safe(default):
    def decorator(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except (RedisError, OSError) as exc:
                logger.error("Redis cache error in %s: %s", method.__name__, exc)
                return default(*args, **kwargs) if callable(default) else default

        return wrapper

    return decorator


class SafeRedisCache(RedisCache):
    """get -> miss, set/add/delete -> no-op when Redis is down (errors are logged, never raised)."""

    get = _safe(lambda self_key, default=None, *a, **k: default)(RedisCache.get)
    get_many = _safe({})(RedisCache.get_many)
    set = _safe(None)(RedisCache.set)
    add = _safe(False)(RedisCache.add)
    delete = _safe(False)(RedisCache.delete)
    has_key = _safe(False)(RedisCache.has_key)
