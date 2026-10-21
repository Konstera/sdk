"""Internal MCP client wrapper.

Isolates the mcp SDK's API shape from the rest of the SDK so evolving upstream
API changes only touch this file. Also provides a no-op fallback when the
kernel MCP URL is unset (direct-run / local-dev mode).
"""
from __future__ import annotations

import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger("konstera_sdk.mcp")


class KernelMcpClient:
    """Session-per-call wrapper around the kernel's MCP endpoint.

    We open a fresh session for each tool call. Small overhead (~10-15 ms) in
    exchange for a much simpler lifecycle — no long-lived context managers to
    thread through the agent's request handling. Persistent sessions become
    a later optimisation once real workloads show it matters.
    """

    def __init__(self, url: str | None):
        self._url = url

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    async def call_tool(self, name: str, args: dict[str, Any]) -> None:
        """Fire-and-forget tool call. Logs but does not raise on failure —
        agent business logic should not break because a log line failed."""
        if not self._url:
            logger.debug("MCP disabled; skipping %s(%s)", name, args)
            return
        try:
            async with streamable_http_client(self._url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.call_tool(name, args)
        except Exception:
            logger.exception("MCP tool call failed: %s", name)

    async def call_tool_for_result(self, name: str, args: dict[str, Any]) -> Any:
        """Version that raises on failure and returns the tool's result.

        Used by services (like llm) where the agent semantically needs the
        response. Failures propagate so agent can decide how to react."""
        if not self._url:
            raise RuntimeError(
                f"Cannot call MCP tool '{name}' — KONSTERA_KERNEL_MCP_URL is unset. "
                f"This is expected in direct-run mode; the agent should guard "
                f"against it or run inside an Konstera kernel."
            )
        async with streamable_http_client(self._url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, args)
        # Interpret (and possibly raise) only after the session has closed: an
        # exception raised inside these context managers is wrapped by anyio in
        # an ExceptionGroup ("unhandled errors in a TaskGroup"), hiding the
        # kernel's message from the agent's log.
        return tool_result_text(name, result)


def tool_result_text(name: str, result: Any) -> str | None:
    """Text of a CallToolResult, or raise if the tool reported an error.

    MCP reports a failed tool as a normal result with isError=true and the
    error message as its content. Returning that text as if it were data made
    kernel failures look like empty/odd results to agents (finding F-13:
    e.g. a failed order lookup became "no orders"), so it raises instead.
    The message keeps the kernel's "[Code] ..." prefix, which callers such as
    CapabilityService map to typed errors.
    """
    texts = [c.text for c in (getattr(result, "content", None) or []) if hasattr(c, "text")]
    text = "".join(texts) if texts else None
    if getattr(result, "is_error", None) or getattr(result, "isError", None):
        raise RuntimeError(text or f"MCP tool '{name}' failed without an error message.")
    return text
