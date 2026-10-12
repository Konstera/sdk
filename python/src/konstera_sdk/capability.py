"""CapabilityService — agent-facing view of the ADR-013 capability layer.

Two operations mirror the kernel MCP tools:

  await ctx.capability.available(name) -> bool
  await ctx.capability.call(name, **args) -> Any  (canonical shape)

Purpose-first indirection over connectors. The agent asks for a canonical
capability (`orders.lookup_by_email`, `tickets.reply`, `knowledge.search`,
`email.send`) — the operator, in the portal, has bound each to a specific
connection at install time.

The agent's code stays vendor-agnostic:

    if await ctx.capability.available("orders.lookup_by_email"):
        orders = await ctx.capability.call("orders.lookup_by_email", email=email)
        # orders is always the canonical shape, no matter what backs it

For optional capabilities (some installs won't bind them), always call
`available()` first — otherwise `call()` raises CapabilityUnbound.
"""
from __future__ import annotations

import json
from typing import Any

from ._invocation_context import current_invocation_id
from ._mcp import KernelMcpClient


class CapabilityError(RuntimeError):
    """Base for capability-related errors surfaced from the kernel."""


class CapabilityUnbound(CapabilityError):
    """The agent has no binding for this capability in the current install.

    Routine — the agent should have checked `available()` first for optional
    capabilities. Not raised for required capabilities because the platform
    blocks agent enable until they're bound (per ADR-013 §Decision).
    """


class CapabilityUpstreamFailed(CapabilityError):
    """The connector or REST recipe backing this capability threw."""


class CapabilityService:
    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def available(self, name: str) -> bool:
        """True iff the operator has bound this capability to a connection
        for this agent instance. Cheap — single DB hit. Use before calling
        optional capabilities.
        """
        raw = await self._mcp.call_tool_for_result(
            "capability_available",
            {"callerInstanceId": self._instance, "name": name},
        )
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return False
        return bool(parsed.get("available", False))

    async def call(self, name: str, /, **args: Any) -> Any:
        """Invoke a capability by canonical name.

        `name` is positional-only so a capability can take an argument called
        `name` itself (db.object.definition, db.proc.stats):
        ``await ctx.capability.call("db.proc.stats", name="dbo.procX")``.

        Args are the canonical arg shape (see capability_catalog for the
        exact schema per capability). Response is always the canonical
        response shape regardless of which connector backs it.

        Raises:
            CapabilityUnbound       — no binding for this capability
            CapabilityUpstreamFailed — underlying connector/recipe failed
            CapabilityError          — other capability-layer failures
        """
        params: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "name": name,
            "argsJson": json.dumps(args, default=str),
        }
        # The invocation this call belongs to. The kernel uses it only to let a
        # human-authored call (a ticket reply after a reviewer approved it) act
        # for that reviewer, after checking it against its own records.
        invocation_id = current_invocation_id()
        if invocation_id:
            params["invocationId"] = invocation_id
        try:
            raw = await self._mcp.call_tool_for_result("capability_call", params)
        except Exception as e:
            # Kernel surfaces CapabilityError sub-codes as
            # "[Unbound] Agent has no binding..." etc — parse the prefix.
            msg = str(e)
            if "[Unbound]" in msg:
                raise CapabilityUnbound(msg) from e
            if "[UpstreamFailed]" in msg or "[ResponseShapeInvalid]" in msg:
                raise CapabilityUpstreamFailed(msg) from e
            raise CapabilityError(msg) from e

        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
