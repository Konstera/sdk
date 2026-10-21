"""Per-invocation ambient context — carries the current `invocation_id`
through the agent's `handle()` call without forcing the agent to thread it
through every service call.

The SDK runtime sets this before dispatching to `agent.handle()` and resets
it after; the LogService (and future services that need correlation) reads
it lazily. Uses `contextvars.ContextVar` so it's safe across `await` +
`asyncio.gather` fan-out — each task inherits the parent's value.

Kept as a module-level singleton (matches the ambient-tenant-scope pattern
on the kernel side; see `AmbientTenantScope.cs`).
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_current_invocation: ContextVar[str | None] = ContextVar(
    "konstera_current_invocation", default=None
)


def current_invocation_id() -> str | None:
    """Read the invocation id in scope for this task, or None."""
    return _current_invocation.get()


@contextmanager
def enter_invocation(invocation_id: str) -> Iterator[None]:
    """Push `invocation_id` onto the ambient context for the duration of the block."""
    token = _current_invocation.set(invocation_id)
    try:
        yield
    finally:
        _current_invocation.reset(token)


__all__ = ["current_invocation_id", "enter_invocation"]
