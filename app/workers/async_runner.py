"""
Run async pipeline code from synchronous Celery tasks.

``asyncio.run()`` creates and destroys an event loop per task, but provider
SDKs (Groq/OpenAI/httpx) keep connection pools bound to the loop they were
created on — the *second* task then fails with "Event loop is closed".

Instead every worker thread keeps one long-lived loop.  If a task is
interrupted (Celery soft time limit), all of its pending coroutines are
cancelled before the loop is reused, so nothing leaks into the next task.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")

_local = threading.local()


def _loop() -> asyncio.AbstractEventLoop:
    loop = getattr(_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _local.loop = loop
    return loop


def run(coro: Coroutine[Any, Any, T]) -> T:
    loop = _loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    except BaseException:
        _cancel_pending(loop)
        raise


def _cancel_pending(loop: asyncio.AbstractEventLoop) -> None:
    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except BaseException:
            pass
