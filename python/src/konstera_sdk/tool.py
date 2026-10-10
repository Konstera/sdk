"""ToolService — call platform-provided tools by name.

M7a ships: datetime_now, datetime_parse, hash_sha256, uuid_new, json_validate.
Discover the full set at runtime with `await ctx.tool.list()`.
"""
from __future__ import annotations

import json
from typing import Any

from ._mcp import KernelMcpClient


class ToolService:
    def __init__(self, mcp: KernelMcpClient):
        self._mcp = mcp

    async def list(self) -> list[dict[str, str]]:
        """Return [{name, description}, ...] for available platform tools."""
        raw = await self._mcp.call_tool_for_result("tool_list", {})
        try:
            return json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []

    async def call(self, name: str, **args: Any) -> Any:
        """Invoke a platform tool. Returns the tool's result decoded from JSON."""
        raw = await self._mcp.call_tool_for_result(
            "tool_call",
            {"name": name, "argsJson": json.dumps(args, default=str)},
        )
        try:
            return json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return raw
