"""
Worker runtime: consecutive tasks must be able to reuse async HTTP clients.

The original worker called ``asyncio.run()`` per task, which closes the
event loop — provider SDK connection pools created during the first task
then fail on the second with "Event loop is closed".
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.workers import async_runner

pytestmark = pytest.mark.integration


def test_cached_async_client_survives_consecutive_tasks():
    from tests.conftest import INTEGRATION_URL

    shared = {}

    async def task() -> int:
        client = shared.setdefault("client", httpx.AsyncClient())
        response = await client.get(f"{INTEGRATION_URL}/rest/v1/")
        return response.status_code

    assert [async_runner.run(task()) for _ in range(3)] == [200, 200, 200]
    async_runner.run(shared["client"].aclose())


def test_interrupted_task_does_not_leak_into_the_next_one():
    finished = []

    async def slow():
        try:
            await asyncio.sleep(3600)
        finally:
            finished.append("cancelled")

    async def interrupted():
        asyncio.get_running_loop().create_task(slow())
        await asyncio.sleep(0)
        raise KeyboardInterrupt  # stands in for Celery's SoftTimeLimitExceeded

    with pytest.raises(KeyboardInterrupt):
        async_runner.run(interrupted())
    assert finished == ["cancelled"]

    async def next_task() -> str:
        return "ok"

    assert async_runner.run(next_task()) == "ok"
