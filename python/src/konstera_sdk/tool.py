"""ToolService — call platform-provided tools by name.

The kernel ships a small set of utility tools (datetime, hashing, UUID generation,
JSON validation) available to any agent without requiring tenant setup. Discover
the available set at runtime with `await ctx.tool.list()`.

M7a ships: `datetime_now`, `datetime_parse`, `hash_sha256`, `uuid_new`,
`json_validate`. New tools land in the kernel over time; `list()` is the
authoritative source for what's available now.

Example:
    >>> now = await ctx.tool.call("datetime_now", tz="UTC")
    >>> digest = await ctx.tool.call("hash_sha256", data="hello")
    >>> idemp_key = await ctx.tool.call("uuid_new")
"""
from __future__ import annotations

import json
from typing import Any

from ._mcp import KernelMcpClient


class ToolService:
    def __init__(self, mcp: KernelMcpClient):
        self._mcp = mcp

    async def list(self) -> list[dict[str, str]]:
        """List platform tools available to this agent.

        Returns:
            List of `{"name": "...", "description": "..."}` dicts. Empty list
            when no tools are available or the kernel response was malformed.

        Example:
            >>> tools = await ctx.tool.list()
            >>> for t in tools:
            ...     print(f"{t['name']}: {t['description']}")
        """
        raw = await self._mcp.call_tool_for_result("tool_list", {})
        try:
            return json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []

    async def call(self, name: str, **args: Any) -> Any:
        """Invoke a platform tool.

        Args:
            name: Tool name from `list()`. e.g. `"datetime_now"`, `"hash_sha256"`.
            **args: Tool-specific keyword arguments. Non-JSON types
                (datetime, Decimal) fall back to `str()` on serialisation.

        Returns:
            The tool's result decoded from JSON. Typically a string, number,
            or dict depending on the tool. `None` for an empty response.
            Non-JSON responses pass through as raw strings (edge case).

        Example:
            >>> # Current UTC time
            >>> now = await ctx.tool.call("datetime_now", tz="UTC")
            >>>
            >>> # SHA-256 for idempotency keys
            >>> digest = await ctx.tool.call("hash_sha256", data="order:12345")
            >>>
            >>> # Validate a JSON schema
            >>> result = await ctx.tool.call(
            ...     "json_validate",
            ...     schema={"type": "object", "required": ["id"]},
            ...     instance={"id": "x"},
            ... )
        """
        raw = await self._mcp.call_tool_for_result(
            "tool_call",
            {"name": name, "argsJson": json.dumps(args, default=str)},
        )
        try:
            return json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return raw
