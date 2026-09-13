"""
DevVision AI - Multi-Tenant Sliding Window Rate Limiter.

Supports:
- Atomic Redis sliding-window operations using Lua script.
- Thread-safe, bounded in-memory sliding-window fallback when Redis is unavailable.
- Deterministic opaque keys scoped per workspace and user.
- RFC-compliant Retry-After calculation and HTTP 429 response generation.
"""

import math
import threading
import time
from collections import deque
from typing import Dict, Optional, Tuple
from fastapi import Request
import structlog

from app.core.config import get_settings
from app.core.exceptions import RateLimitException
from app.core.redis import get_redis_client

logger = structlog.get_logger(__name__)

# Redis Lua Script for atomic sliding-window rate limiting
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local clearBefore = now - window

redis.call('ZREMRANGEBYSCORE', key, 0, clearBefore)
local currentRequests = redis.call('ZCARD', key)

if currentRequests < limit then
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, math.ceil(window))
    return {1, limit - currentRequests - 1, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retryAfter = 1
    if oldest and #oldest >= 2 then
        retryAfter = math.ceil((tonumber(oldest[2]) + window) - now)
    end
    if retryAfter < 1 then retryAfter = 1 end
    return {0, 0, retryAfter}
end
"""


class InMemorySlidingWindow:
    """Thread-safe bounded in-memory sliding-window rate limiter."""

    def __init__(self, max_keys: int = 10000):
        self._lock = threading.Lock()
        self._storage: Dict[str, deque] = {}
        self._last_cleanup = time.monotonic()
        self._max_keys = max_keys

    def is_allowed(self, key: str, limit: int, window: float) -> Tuple[bool, int, int]:
        now = time.time()
        clear_before = now - window

        with self._lock:
            # Periodic cleanup of idle keys every 60 seconds or if map exceeds max_keys
            if time.monotonic() - self._last_cleanup > 60.0 or len(self._storage) > self._max_keys:
                self._cleanup(now)

            if key not in self._storage:
                self._storage[key] = deque()

            bucket = self._storage[key]
            while bucket and bucket[0] <= clear_before:
                bucket.popleft()

            if len(bucket) < limit:
                bucket.append(now)
                remaining = limit - len(bucket)
                return True, remaining, 0
            else:
                oldest = bucket[0]
                retry_after = max(1, math.ceil((oldest + window) - now))
                return False, 0, retry_after

    def _cleanup(self, now: float):
        self._last_cleanup = time.monotonic()
        keys_to_delete = []
        for k, b in self._storage.items():
            # If bucket is empty or oldest entry is older than 2 minutes, prune
            if not b or (now - b[-1]) > 120.0:
                keys_to_delete.append(k)
        for k in keys_to_delete:
            del self._storage[k]

    def reset(self):
        with self._lock:
            self._storage.clear()


class RateLimiter:
    """Hybrid rate limiter with Redis backend and in-memory fallback."""

    def __init__(self):
        self.in_memory = InMemorySlidingWindow()
        self._lua_sha: Optional[str] = None

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, int]:
        """
        Evaluates whether an action is permitted within the rate limit.
        Returns (is_allowed, remaining, retry_after).
        """
        settings = get_settings()
        if not settings.RATE_LIMIT_ENABLED:
            return True, limit, 0

        # Try Redis if available
        try:
            client = get_redis_client()
            now = time.time()
            res = await client.eval(SLIDING_WINDOW_LUA, 1, key, now, window_seconds, limit)
            allowed = bool(res[0])
            remaining = int(res[1])
            retry_after = int(res[2])
            return allowed, remaining, retry_after
        except Exception as exc:
            # Fall back safely to in-memory limiter without blocking or failing requests
            logger.debug("redis_rate_limit_fallback_in_memory", error=str(exc))
            return self.in_memory.is_allowed(key, limit, float(window_seconds))


limiter = RateLimiter()


def rate_limit(action: str, limit_getter):
    """
    FastAPI dependency enforcing workspace-aware and user-aware rate limits.
    limit_getter is either an integer or a callable returning an integer.
    """
    async def _dependency(request: Request):
        settings = get_settings()
        if not settings.RATE_LIMIT_ENABLED:
            return

        limit = limit_getter() if callable(limit_getter) else limit_getter

        # Extract workspace_id and user context
        workspace_id = request.path_params.get("workspace_id")
        user = getattr(request.state, "user", None)
        user_id = getattr(user, "id", None) or getattr(request.state, "user_id", None)

        # Build opaque deterministic key
        if workspace_id and user_id:
            key = f"rl:{action}:{workspace_id}:{user_id}"
        elif workspace_id:
            client_ip = request.client.host if request.client else "unknown"
            key = f"rl:{action}:{workspace_id}:{client_ip}"
        else:
            client_ip = request.client.host if request.client else "unknown"
            key = f"rl:{action}:{client_ip}"

        allowed, remaining, retry_after = await limiter.check_rate_limit(key, limit, window_seconds=60)
        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                action=action,
                key=key,
                retry_after=retry_after,
            )
            raise RateLimitException(
                message=f"Rate limit exceeded for {action}. Please try again in {retry_after} seconds.",
                retry_after=retry_after,
            )

    return _dependency
