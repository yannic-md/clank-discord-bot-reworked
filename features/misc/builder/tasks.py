import asyncio
from collections.abc import Coroutine
from typing import Any

_background_tasks: set[asyncio.Task[None]] = set()


def run_in_background(coro: Coroutine[Any, Any, None]) -> None:
    """Fire-and-forget `coro`, holding a strong reference until it finishes so the
    event loop does not garbage-collect the task mid-flight."""
    task: asyncio.Task[None] = asyncio.create_task(coro)

    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
