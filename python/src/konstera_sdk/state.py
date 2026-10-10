"""StateService — thin wrapper around the kernel MCP `state_*` tools.

State is a durable KV per agent instance, scoped by tenant. Values are
JSON — dicts, lists, strings, numbers, booleans, or None all work.
"""
from __future__ import annotations

import json
from typing import Any

from ._mcp import KernelMcpClient


class StateService:
    """Per-instance durable KV. All operations use the agent's own instance ID."""

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def get(self, key: str) -> Any:
        """Return the value for `key` as decoded JSON, or None if not set."""
        raw = await self._mcp.call_tool_for_result(
            "state_get", {"instanceId": self._instance, "key": key}
        )
        # kernel returns the JSON value as-is; deserialise for the caller
        if raw is None or raw == "null":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(self, key: str, value: Any) -> None:
        """Upsert `key` = `value`. `value` is JSON-encoded here."""
        await self._mcp.call_tool_for_result(
            "state_set",
            {
                "instanceId": self._instance,
                "key": key,
                "valueJson": json.dumps(value, default=str),
            },
        )

    async def delete(self, key: str) -> None:
        """Idempotent — deleting a missing key is fine."""
        await self._mcp.call_tool_for_result(
            "state_delete", {"instanceId": self._instance, "key": key}
        )

    async def list(self, prefix: str = "") -> list[str]:
        """List keys (optionally filtered by a prefix). Returns [] on empty."""
        raw = await self._mcp.call_tool_for_result(
            "state_list", {"instanceId": self._instance, "prefix": prefix}
        )
        try:
            return json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []
