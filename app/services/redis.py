"""
Redis client initialisation and helper functions for TrueAI.

Design notes
────────────
- The client is a ``redis.Redis`` instance backed by a connection pool,
  which is thread-safe and suitable for multi-threaded WSGI/ASGI workers.
- ``decode_responses=True`` is set globally: all keys and values are Python
  strings rather than bytes, eliminating decode boilerplate at call sites.
- Every operation is wrapped in try/except.  Redis failures are logged at
  ERROR level but never re-raised: the callers (pipeline nodes, Celery tasks)
  are responsible for deciding whether a cache miss / queue failure is fatal.
- ``is_duplicate`` uses a single atomic ``SET NX EX`` command.  This is the
  only correct way to implement distributed deduplication — a manual GET +
  SET sequence has an unavoidable race condition where two concurrent workers
  can both see "key absent" and both proceed to process the same event.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional

import redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------ #
# Singleton                                                            #
# ------------------------------------------------------------------ #

_redis_client: Optional[redis.Redis] = None
_redis_lock: threading.Lock = threading.Lock()

# Key namespace prefix applied to all dedup keys to avoid collisions with
# other applications sharing the same Redis instance.
_DEDUP_PREFIX: str = "trueai:dedup:"

# Prefix for generic application cache keys.
_CACHE_PREFIX: str = "trueai:cache:"


def get_redis() -> redis.Redis:
    """
    Return the shared :class:`redis.Redis` singleton.

    Constructed lazily on the first call.  The underlying connection pool
    is thread-safe and reconnects automatically on transient network errors.

    Returns:
        A configured :class:`redis.Redis` client with ``decode_responses=True``.

    Raises:
        :class:`redis.exceptions.ConnectionError`: If the Redis server is
            unreachable at first connection attempt.  This propagates to crash
            the worker/API process early rather than fail silently at runtime.
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    with _redis_lock:
        if _redis_client is not None:   # double-checked locking
            return _redis_client

        logger.info("Initialising Redis client (url=%s).", _mask_redis_url(settings.REDIS_URL))
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,      # seconds to wait for initial connection
            socket_timeout=10,             # seconds for individual command execution
            health_check_interval=30,      # keepalive ping interval
            retry_on_timeout=True,
            max_connections=50,
        )
        # Validate connectivity eagerly so startup fails fast on
        # misconfiguration rather than at the first queue operation.
        _redis_client.ping()
        logger.info("Redis client ready.")

    return _redis_client


def reset_redis() -> None:
    """
    Discard the cached Redis client so the next :func:`get_redis` call
    constructs a fresh one.  Intended for use in tests.
    """
    global _redis_client
    with _redis_lock:
        if _redis_client is not None:
            try:
                _redis_client.close()
            except Exception:
                pass
        _redis_client = None
    logger.debug("Redis client cache cleared.")


# ------------------------------------------------------------------ #
# Task queue helpers                                                   #
# ------------------------------------------------------------------ #

def push_task(queue_name: str, data: Dict[str, Any]) -> bool:
    """
    Serialise *data* to JSON and push it onto a Redis list (FIFO queue).

    Workers consume tasks with ``BLPOP queue_name 0`` (blocking left-pop).
    We push to the right (``RPUSH``) so that tasks are processed in the
    order they arrived.

    Args:
        queue_name: Name of the Redis list to push to.
        data:       Task payload (must be JSON-serialisable).

    Returns:
        ``True`` if the task was enqueued successfully, ``False`` on error.
    """
    try:
        serialised = json.dumps(data, default=str)
        client = get_redis()
        depth: int = client.rpush(queue_name, serialised)
        logger.debug(
            "push_task: enqueued to '%s' (queue depth now %d).",
            queue_name,
            depth,
        )
        return True

    except (TypeError, ValueError) as exc:
        logger.error(
            "push_task: JSON serialisation failed for queue '%s': %s — %s.",
            queue_name,
            type(exc).__name__,
            exc,
        )
        return False

    except RedisError as exc:
        logger.error(
            "push_task: Redis error pushing to queue '%s': %s — %s.",
            queue_name,
            type(exc).__name__,
            exc,
        )
        return False


# ------------------------------------------------------------------ #
# Deduplication                                                        #
# ------------------------------------------------------------------ #

def is_duplicate(event_id: str, ttl_seconds: int = 3600) -> bool:
    """
    Atomically check whether *event_id* has been seen before.

    Uses a single ``SET key value NX EX ttl`` command which is atomic on the
    Redis server.  There is no race condition: if two workers call this
    function concurrently for the same *event_id*, exactly one will receive
    ``True`` (the SET succeeded → first seen) and the other will receive
    ``False`` (the SET was skipped because the key already existed → duplicate).

    Args:
        event_id:    Unique event identifier (e.g. Sentry ``event_id`` UUID).
        ttl_seconds: How long to remember the event.  After this many seconds
                     the key expires and the same event_id would be treated
                     as new again.  Defaults to 1 hour.

    Returns:
        ``True``  — this event_id was seen before (duplicate; skip processing).
        ``False`` — this event_id is new (process it).

        On Redis errors, returns ``False`` to fail **open** — it is safer to
        process a potential duplicate than to drop a real incident.
    """
    key = f"{_DEDUP_PREFIX}{event_id}"
    try:
        client = get_redis()

        # SET key "1" NX EX ttl_seconds
        # Returns True  → key was set   → first occurrence → NOT a duplicate
        # Returns None  → key existed   → already seen     → IS a duplicate
        result = client.set(key, "1", nx=True, ex=ttl_seconds)

        is_dup: bool = result is None
        if is_dup:
            logger.debug(
                "is_duplicate: duplicate event detected (event_id=%s).", event_id
            )
        return is_dup

    except RedisError as exc:
        logger.error(
            "is_duplicate: Redis error for event_id=%s: %s — %s. "
            "Failing open (treating as non-duplicate).",
            event_id,
            type(exc).__name__,
            exc,
        )
        return False


# ------------------------------------------------------------------ #
# Generic cache helpers                                                #
# ------------------------------------------------------------------ #

def cache_set(key: str, value: Any, ttl: int) -> bool:
    """
    Serialise *value* to JSON and store it under *key* with a TTL.

    Args:
        key:   Cache key (the ``trueai:cache:`` prefix is prepended
               automatically to namespace away from other Redis users).
        value: Any JSON-serialisable Python object.
        ttl:   Time-to-live in seconds.  Must be > 0.

    Returns:
        ``True`` on success, ``False`` on any error.
    """
    if ttl <= 0:
        logger.warning(
            "cache_set: called with ttl=%d for key='%s' — skipped.", ttl, key
        )
        return False

    namespaced_key = f"{_CACHE_PREFIX}{key}"
    try:
        serialised = json.dumps(value, default=str)
        client = get_redis()
        client.setex(namespaced_key, ttl, serialised)
        logger.debug(
            "cache_set: stored key='%s' (ttl=%ds, size=%d bytes).",
            namespaced_key,
            ttl,
            len(serialised),
        )
        return True

    except (TypeError, ValueError) as exc:
        logger.error(
            "cache_set: JSON serialisation failed for key='%s': %s — %s.",
            key,
            type(exc).__name__,
            exc,
        )
        return False

    except RedisError as exc:
        logger.error(
            "cache_set: Redis error for key='%s': %s — %s.",
            key,
            type(exc).__name__,
            exc,
        )
        return False


def cache_get(key: str) -> Optional[Any]:
    """
    Retrieve and deserialise the cached value for *key*.

    Args:
        key: Cache key (same value passed to :func:`cache_set`).

    Returns:
        The deserialised Python object, or ``None`` on a cache miss or error.
        Callers cannot distinguish a cache miss from a Redis error — both
        return ``None`` so the caller falls through to the source of truth.
    """
    namespaced_key = f"{_CACHE_PREFIX}{key}"
    try:
        client = get_redis()
        raw: Optional[str] = client.get(namespaced_key)

        if raw is None:
            logger.debug("cache_get: miss for key='%s'.", namespaced_key)
            return None

        value = json.loads(raw)
        logger.debug("cache_get: hit for key='%s'.", namespaced_key)
        return value

    except json.JSONDecodeError as exc:
        logger.error(
            "cache_get: failed to deserialise value for key='%s': %s.",
            key,
            exc,
        )
        return None

    except RedisError as exc:
        logger.error(
            "cache_get: Redis error for key='%s': %s — %s.",
            key,
            type(exc).__name__,
            exc,
        )
        return None


def cache_delete(key: str) -> bool:
    """
    Delete a cached key.

    Args:
        key: Cache key to delete (the ``trueai:cache:`` prefix is applied).

    Returns:
        ``True`` if the key existed and was deleted, ``False`` otherwise
        (including errors).
    """
    namespaced_key = f"{_CACHE_PREFIX}{key}"
    try:
        client = get_redis()
        deleted: int = client.delete(namespaced_key)
        existed = deleted > 0
        logger.debug(
            "cache_delete: key='%s' %s.",
            namespaced_key,
            "deleted" if existed else "was not present",
        )
        return existed

    except RedisError as exc:
        logger.error(
            "cache_delete: Redis error for key='%s': %s — %s.",
            key,
            type(exc).__name__,
            exc,
        )
        return False


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _mask_redis_url(url: str) -> str:
    """
    Redact credentials from a Redis URL for safe logging.

    ``redis://:password@host:port/db`` → ``redis://:****@host:port/db``
    ``rediss://user:pass@host:6380/1`` → ``rediss://user:****@host:6380/1``
    """
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            safe = parsed._replace(
                netloc=parsed.netloc.replace(f":{parsed.password}", ":****")
            )
            return urlunparse(safe)
    except Exception:
        pass
    return url

