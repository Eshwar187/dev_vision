from typing import Optional
import redis.asyncio as aioredis
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("redis")
settings = get_settings()

redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Initializes or returns the global async Redis client."""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return redis_client


async def close_redis_client() -> None:
    """Closes the Redis client connection pool."""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None
        logger.info("Redis connection pool closed.")


async def check_redis_health() -> bool:
    """Executes a Redis PING check."""
    try:
        client = get_redis_client()
        pong = await client.ping()
        return bool(pong)
    except Exception as exc:
        logger.error("Redis health check failed", error=str(exc))
        return False
