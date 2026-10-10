"""AgentsService — invoke another agent instance synchronously.

M7a: goes through the kernel's HTTP invoke path. Target instance must
already be loaded on the kernel. M11 replaces this with Temporal child
workflows.

M8: kernel enforces same-tenant callee (see kernel AgentsService.Invoke).
Caller instance UUID is injected automatically on every call.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ._mcp import KernelMcpClient


@dataclass(slots=True, frozen=True)
class AgentInvokeResult:
    target_instance_id: str
    invocation_id: str
    response: dict[str, Any]


class AgentsService:
    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def invoke(
        self,
        target_instance_id: str,
        input: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> AgentInvokeResult:
        """Invoke another loaded agent by instance UUID. Blocks until it
        returns or the timeout fires. Requires the target to already be
        loaded — kernel deliberately does not spawn on-demand from here.
        M8: target must belong to the same tenant as the caller."""
        args: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "targetInstanceId": target_instance_id,
            "input": input,
        }
        if payload is not None:
            args["payloadJson"] = json.dumps(payload, default=str)
        if timeout_seconds is not None:
            args["timeoutSeconds"] = timeout_seconds

        raw = await self._mcp.call_tool_for_result("agents_invoke", args)
        data = json.loads(raw) if raw else {}
        return AgentInvokeResult(
            target_instance_id=str(data.get("targetInstanceId", target_instance_id)),
            invocation_id=str(data.get("invocationId", "")),
            response=data.get("response") or {},
        )
