"""CostService — record non-LLM cost events. LLM costs will flow through
`ctx.llm.complete()` automatically once M10's real adapters land.
"""
from __future__ import annotations

import json
from typing import Any

from ._mcp import KernelMcpClient


class CostService:
    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def record(
        self,
        *,
        kind: str,
        cost_usd: float,
        model: str | None = None,
        invocation_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a usage event. `kind` is a short label — llm, tool,
        connector, other. `cost_usd` must be >= 0."""
        args: dict[str, Any] = {
            "instanceId": self._instance,
            "kind": kind,
            "costUsd": cost_usd,
        }
        if invocation_id is not None:
            args["invocationId"] = invocation_id
        if model is not None:
            args["modelId"] = model
        if input_tokens is not None:
            args["inputTokens"] = input_tokens
        if output_tokens is not None:
            args["outputTokens"] = output_tokens
        if cached_input_tokens is not None:
            args["cachedInputTokens"] = cached_input_tokens
        if metadata:
            args["metadataJson"] = json.dumps(metadata, default=str)
        await self._mcp.call_tool_for_result("cost_record", args)
