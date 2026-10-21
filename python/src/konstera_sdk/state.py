"""StateService — thin wrapper around the kernel MCP `state_*` tools.

State is a durable KV per agent instance, scoped by tenant. Values are
JSON — dicts, lists, strings, numbers, booleans, or None all work.
"""
from __future__ import annotations

import json
from typing import Any

from ._mcp import KernelMcpClient


class StateService:
    """Per-instance durable KV, tenant-scoped by the kernel.

    State persists across invocations and across container restarts. Values
    are JSON — dicts, lists, strings, numbers, booleans, or None all work.
    Non-JSON types (datetime, Decimal) are coerced via `str()` on set.

    State is **per agent instance**, not per invocation. Use it for things
    that should outlive one `handle()` call — counters, caches, cursor
    positions, drafted-but-not-sent artifacts.

    Example:
        >>> # Increment a counter across invocations
        >>> count = (await ctx.state.get("processed_count")) or 0
        >>> await ctx.state.set("processed_count", count + 1)
        >>>
        >>> # Cache structured data
        >>> await ctx.state.set("profile", {"name": "Alice", "tier": "gold"})
        >>> profile = await ctx.state.get("profile")
        >>> profile["tier"]
        'gold'
    """

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def get(self, key: str) -> Any:
        """Fetch the value for `key`.

        Args:
            key: The storage key. No prefix convention is enforced, but a
                `namespace:name` pattern is a useful convention when the
                agent manages multiple kinds of state.

        Returns:
            The decoded JSON value, or `None` if the key is unset.
            Scalars (strings, numbers, booleans), dicts, and lists all
            decode to their native Python types. Non-JSON responses
            (e.g. from an older kernel) are returned as the raw string.

        Example:
            >>> cursor = await ctx.state.get("last_processed_id")
            >>> if cursor is None:
            ...     cursor = "0000"  # first run
        """
        raw = await self._mcp.call_tool_for_result(
            "state_get", {"instanceId": self._instance, "key": key}
        )
        if raw is None or raw == "null":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(self, key: str, value: Any) -> None:
        """Upsert `key = value`.

        Args:
            key: The storage key.
            value: Any JSON-serialisable value. `datetime`, `Decimal`, and
                similar non-JSON types fall back to `str()`.

        Example:
            >>> await ctx.state.set(
            ...     "config",
            ...     {"max_retries": 3, "fail_fast": True},
            ... )
        """
        await self._mcp.call_tool_for_result(
            "state_set",
            {
                "instanceId": self._instance,
                "key": key,
                "valueJson": json.dumps(value, default=str),
            },
        )

    async def delete(self, key: str) -> None:
        """Remove `key`. Idempotent — deleting a missing key is a no-op.

        Args:
            key: The storage key to remove.
        """
        await self._mcp.call_tool_for_result(
            "state_delete", {"instanceId": self._instance, "key": key}
        )

    async def list(self, prefix: str = "") -> list[str]:
        """List keys, optionally filtered by prefix.

        Args:
            prefix: Only return keys starting with this string. Empty string
                (the default) returns all keys.

        Returns:
            Sorted list of keys. Empty list when none match or the kernel
            returned a malformed response.

        Example:
            >>> # List all cached customer profiles
            >>> customer_keys = await ctx.state.list(prefix="customer:")
        """
        raw = await self._mcp.call_tool_for_result(
            "state_list", {"instanceId": self._instance, "prefix": prefix}
        )
        try:
            return json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []
