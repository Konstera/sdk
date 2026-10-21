"""CostService — record non-LLM cost events.

LLM costs are recorded automatically by the kernel on every `ctx.llm.complete()`
call — agents never need to call this for LLM spend. Use `ctx.cost.record()`
for cost events the kernel can't infer: external API spend, GPU time on a
non-managed inference endpoint, third-party scoring services, etc.

Example:
    >>> # Record spend after calling a non-kernel inference service
    >>> result = await external_inference_api.rank(query, candidates)
    >>> await ctx.cost.record(
    ...     kind="tool",
    ...     cost_usd=result.cost_usd,
    ...     metadata={"vendor": "cohere", "model": "rerank-english-v3.0"},
    ... )
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
        """Record a usage event.

        Args:
            kind: Short label — `"llm"`, `"tool"`, `"connector"`, `"other"`.
                Appears in cost reports in the portal.
            cost_usd: Cost in USD. Must be >= 0. Zero is valid
                (e.g. cached response, free tier).
            model: Model identifier if the cost is from an LLM-like call.
                Routes the event to the model-level cost view in the portal.
            invocation_id: Override for the current invocation's ID. Rarely
                needed — the SDK normally injects the ambient invocation ID.
            input_tokens: Input/prompt tokens if applicable. Passing `0`
                explicitly is kept and reported as a zero-token event (which
                is semantically distinct from "not reported").
            output_tokens: Output/completion tokens if applicable.
            cached_input_tokens: Tokens served from provider-side cache
                (Anthropic + OpenAI both report this separately — the kernel
                tracks it so cost reports can show the cached-vs-fresh split).
            metadata: Arbitrary JSON-serialisable key/value pairs. Non-JSON
                types (datetime, Decimal) fall back to `str()`.

        Returns:
            None. Fire-and-forget; failures are logged kernel-side but don't
            raise to the agent.

        Example:
            >>> # Record an external reranker call
            >>> await ctx.cost.record(
            ...     kind="tool",
            ...     cost_usd=0.0023,
            ...     model="cohere-rerank-english-v3.0",
            ...     input_tokens=512,
            ...     metadata={"candidates_reranked": 50},
            ... )
        """
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
