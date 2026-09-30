"""
Redis client and primitives used across the API and the worker.

- ``claim_once``  — atomic ``SET NX EX`` used for idempotency (event dedup,
  OAuth nonce single-use, throttles).
- ``lock``        — short best-effort distributed lock (incident grouping).
- ``incr_window`` — fixed-window counter used by the rate limiter.
- JSON cache helpers with namespacing.

Every helper fails *open* (returns the permissive answer) and logs when Redis
is unavailable: losing Redis must degrade protection, never drop incidents
or lock users out.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "trueai:"
_client: Optional[redis.Redis] = None
_lock = threading.Lock()


def get_redis() -> redis.Redis:
    """Return the shared client (connection-pooled and thread-safe)."""
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is None:
            _client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=5,
                health_check_interval=30,
                retry_on_timeout=True,
                max_connections=50,
            )
    return _client


def ping() -> bool:
    try:
        return bool(get_redis().ping())
    except RedisError as exc:
        logger.warning("Redis ping failed: %s", exc)
        return False


def reset_redis() -> None:
    """Close and forget the client (shutdown and tests)."""
    global _client
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:  # pragma: no cover
                pass
        _client = None


def key(*parts: str) -> str:
    return _PREFIX + ":".join(parts)


# ------------------------------------------------------------------ #
# Idempotency / single-use                                             #
# ------------------------------------------------------------------ #

def claim_once(name: str, ttl_seconds: int, value: str = "1") -> Optional[bool]:
    """
    Atomically claim *name* for *ttl_seconds*.

    Returns True when this caller claimed it first, False when it was already
    claimed, and None when Redis is unavailable (caller decides; usually
    proceed = fail open).
    """
    try:
        return bool(get_redis().set(key(name), value, nx=True, ex=max(1, ttl_seconds)))
    except RedisError as exc:
        logger.error("claim_once(%s) failed — Redis unavailable: %s", name, exc)
        return None


def release(name: str) -> None:
    try:
        get_redis().delete(key(name))
    except RedisError as exc:
        logger.warning("release(%s) failed: %s", name, exc)


def pop_value(name: str) -> Optional[str]:
    """Atomically read-and-delete (GETDEL) — used for single-use tokens."""
    try:
        client = get_redis()
        pipe = client.pipeline()
        pipe.get(key(name))
        pipe.delete(key(name))
        value, _ = pipe.execute()
        return value
    except RedisError as exc:
        logger.error("pop_value(%s) failed: %s", name, exc)
        return None


def set_value(name: str, value: str, ttl_seconds: int) -> bool:
    try:
        get_redis().set(key(name), value, ex=max(1, ttl_seconds))
        return True
    except RedisError as exc:
        logger.error("set_value(%s) failed: %s", name, exc)
        return False


@contextmanager
def lock(name: str, *, ttl_seconds: int = 15, wait_seconds: float = 3.0) -> Iterator[bool]:
    """
    Best-effort distributed lock.  Yields True when acquired, False when it
    could not be acquired in time or Redis is down (the caller proceeds —
    the database remains the source of truth).
    """
    token = uuid.uuid4().hex
    lock_key = key("lock", name)
    acquired = False
    deadline = time.monotonic() + wait_seconds
    try:
        client = get_redis()
        while True:
            if client.set(lock_key, token, nx=True, ex=ttl_seconds):
                acquired = True
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    except RedisError as exc:
        logger.warning("lock(%s) unavailable: %s", name, exc)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                # Delete only if we still own it (compare-and-delete).
                get_redis().eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                    1,
                    lock_key,
                    token,
                )
            except RedisError as exc:  # pragma: no cover
                logger.warning("lock(%s) release failed: %s", name, exc)


# ------------------------------------------------------------------ #
# Counters                                                             #
# ------------------------------------------------------------------ #

def incr_window(name: str, window_seconds: int) -> Optional[int]:
    """Increment a fixed-window counter; returns the new count or None if Redis is down."""
    bucket = int(time.time() // window_seconds)
    counter_key = key("rl", name, str(bucket))
    try:
        pipe = get_redis().pipeline()
        pipe.incr(counter_key)
        pipe.expire(counter_key, window_seconds + 1)
        count, _ = pipe.execute()
        return int(count)
    except RedisError as exc:
        logger.warning("Rate limiter unavailable (failing open): %s", exc)
        return None


def window_reset_seconds(window_seconds: int) -> int:
    return int(window_seconds - (time.time() % window_seconds)) or window_seconds


# ------------------------------------------------------------------ #
# JSON cache                                                           #
# ------------------------------------------------------------------ #

def cache_get(name: str) -> Optional[Any]:
    try:
        raw = get_redis().get(key("cache", name))
    except RedisError as exc:
        logger.debug("cache_get(%s) unavailable: %s", name, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def cache_set(name: str, value: Any, ttl_seconds: int) -> None:
    try:
        payload = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return
    if len(payload) > 5_000_000:  # never push multi-MB blobs into Redis
        return
    try:
        get_redis().set(key("cache", name), payload, ex=max(1, ttl_seconds))
    except RedisError as exc:
        logger.debug("cache_set(%s) unavailable: %s", name, exc)
