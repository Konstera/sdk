"""LogService — thin wrapper around the kernel MCP `log_*` tools.

Structured logging that lands in the kernel's `invocation_logs` table, keyed
by the ambient `invocation_id`, and mirrored to the kernel's own log sink
for infra-side aggregation.

Fire-and-forget — these calls never raise. Direct-run mode (no kernel URL)
skips the write silently; a lost log line is preferable to crashing an
agent on a transport hiccup.

Example:
    >>> # Inside Agent.handle:
    >>> await ctx.log.info("processing refund", order_id=order_id, amount_usd=42.50)
    >>> await ctx.log.warn("rate limit near", retries_remaining=1)
    >>> await ctx.log.error("payment provider failed", provider="stripe", code=503)
"""
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
        """Log at INFO level with optional structured fields.

        Args:
            message: Human-readable log message.
            **fields: Arbitrary key/value pairs. Any JSON-serialisable value
                works; `datetime`, `Decimal`, etc. fall back to `str()`.

        Example:
            >>> await ctx.log.info(
            ...     "found customer", customer_id="c-42", lookup_took_ms=12,
            ... )
        """
        await self._mcp.call_tool("log_info", self._payload(message, fields))

    async def warn(self, message: str, **fields: Any) -> None:
        """Log at WARN level — recoverable issue, likely retried.

        Args:
            message: Human-readable log message.
            **fields: Arbitrary key/value pairs.
        """
        await self._mcp.call_tool("log_warn", self._payload(message, fields))

    async def error(self, message: str, **fields: Any) -> None:
        """Log at ERROR level — invocation failing or badly degraded.

        Args:
            message: Human-readable log message.
            **fields: Arbitrary key/value pairs. Include enough context
                (ids, inputs) to diagnose from the log alone.
        """
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
