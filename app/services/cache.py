import json
import logging
import hashlib
from typing import Any, Optional
import redis.asyncio as aioredis
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Lazy singleton — created on first use
_redis: Optional[aioredis.Redis] = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


def _make_key(prefix: str, params: dict) -> str:
    """Deterministic cache key from a dict of query params."""
    stable = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.md5(stable.encode()).hexdigest()[:10]
    return f"shamba:{prefix}:{digest}"


async def get_cached(key: str) -> Optional[Any]:
    try:
        raw = await _get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Cache GET failed for {key}: {e}")
        return None


async def set_cached(key: str, value: Any, ttl: int) -> None:
    try:
        await _get_redis().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        logger.warning(f"Cache SET failed for {key}: {e}")


async def invalidate_prefix(prefix: str) -> int:
    """Delete all keys matching shamba:{prefix}:*  — called after scrape."""
    try:
        r = _get_redis()
        keys = await r.keys(f"shamba:{prefix}:*")
        if keys:
            await r.delete(*keys)
        return len(keys)
    except Exception as e:
        logger.warning(f"Cache INVALIDATE failed for prefix={prefix}: {e}")
        return 0


async def invalidate_all() -> int:
    """Bust every shamba:* key. Called after a successful scrape run."""
    try:
        r = _get_redis()
        keys = await r.keys("shamba:*")
        if keys:
            await r.delete(*keys)
        return len(keys)
    except Exception as e:
        logger.warning(f"Cache full invalidate failed: {e}")
        return 0
