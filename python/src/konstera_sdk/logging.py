"""LogService — thin wrapper around the kernel MCP `log_*` tools."""
from __future__ import annotations

import json
from typing import Any

from ._invocation_context import current_invocation_id
from ._mcp import KernelMcpClient


class LogService:
    """Structured logging back to the kernel via MCP.

    Fields (kwargs) are JSON-serialised and passed to the kernel, which
    resolves the caller's tenant, writes the row to `invocation_logs`
    (keyed by the ambient `invocation_id`), and mirrors to its own log
    sink for infra-side aggregation.

    Backward-compat: if there's no invocation in scope (e.g. from
    `initialize()` before `handle()` fires), the kernel-side write is
    skipped but the mirror log still fires — better a lost correlation
    than a lost log line.
    """

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance_id = instance_id

    async def info(self, message: str, **fields: Any) -> None:
        await self._mcp.call_tool("log_info", self._payload(message, fields))

    async def warn(self, message: str, **fields: Any) -> None:
        await self._mcp.call_tool("log_warn", self._payload(message, fields))

    async def error(self, message: str, **fields: Any) -> None:
        await self._mcp.call_tool("log_error", self._payload(message, fields))

    def _payload(self, message: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "callerInstanceId": self._instance_id,
            "message": message,
            "fields": json.dumps(fields, separators=(",", ":"), default=str) if fields else "{}",
        }
        inv_id = current_invocation_id()
        if inv_id:
            payload["invocationId"] = inv_id
        return payload
