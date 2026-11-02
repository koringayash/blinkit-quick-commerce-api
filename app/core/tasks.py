"""Safe fire-and-forget background tasks.

asyncio only keeps a weak reference to tasks, so a bare `asyncio.create_task(...)` can be
garbage-collected mid-flight and its exceptions are silently lost. `spawn` keeps a strong
reference until the task finishes and logs any failure.
"""
import asyncio
from collections.abc import Coroutine
from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.tasks")

_background_tasks: set[asyncio.Task] = set()


def _on_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            f"Background task {task.get_name()} failed: {exc}",
            exc_info=(type(exc), exc, exc.__traceback__),
        )


def spawn(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task:
    """Schedule `coro` in the background. The current request_id context is inherited."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_on_done)
    return task

