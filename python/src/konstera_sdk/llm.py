"""LlmService — thin wrapper around the kernel MCP `llm_complete` tool.

Two calling shapes (ADR-011 §2):
  1. `ctx.llm.complete(purpose="narrator", prompt=...)` — RECOMMENDED.
     Kernel resolves the tenant's binding for this purpose → concrete
     model + credentials + budget cap. Tenant admin can rebind without
     touching agent code.
  2. `ctx.llm.complete(model="gpt-4o-mini", prompt=...)` — escape hatch.
     Bypasses purpose indirection; kernel picks the provider by model
     prefix. Kept for backwards compat + one-off scripts.

The agent never manages LLM API keys — they live in the tenant's
credentials table under well-known names (ANTHROPIC_API_KEY etc), and
the mapping from provider → credential key lives in llm_provider_configs.
Cost is metered automatically into usage_events on every call.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ._invocation_context import current_invocation_id
from ._mcp import KernelMcpClient


@dataclass(slots=True, frozen=True)
class LlmResult:
    """Structured LLM response. Cost is USD and computed kernel-side from the
    returned token counts × the model's catalogue price."""
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cost_usd: float
    stop_reason: str | None
    # The purpose the caller requested, echoed back for observability.
    # Null when the caller supplied `model=` directly.
    purpose: str | None = None


class LlmService:
    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def complete(
        self,
        prompt: str,
        *,
        purpose: str | None = None,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        invocation_id: str | None = None,
    ) -> LlmResult:
        """Complete against an LLM. Pass either `purpose` (preferred) or
        `model`. See module docstring for the difference.

        Cost is recorded automatically — you do NOT need to call
        `ctx.cost.record` for LLM calls.
        """
        if not purpose and not model:
            raise ValueError("ctx.llm.complete: must supply either `purpose` or `model`.")

        args: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "prompt": prompt,
        }
        if purpose is not None:
            args["purpose"] = purpose
        if model is not None:
            args["model"] = model
        if system is not None:
            args["system"] = system
        if temperature is not None:
            args["temperature"] = temperature
        if max_tokens is not None:
            args["maxTokens"] = max_tokens
        # Explicit invocation_id wins; otherwise auto-inject from ambient
        # invocation context set by the SDK runtime.
        effective_inv = invocation_id or current_invocation_id()
        if effective_inv is not None:
            args["invocationId"] = effective_inv

        raw = await self._mcp.call_tool_for_result("llm_complete", args)
        return _parse(raw)


def _parse(raw: str | None) -> LlmResult:
    if not raw:
        raise RuntimeError("llm_complete returned no result")
    d = json.loads(raw)
    return LlmResult(
        content=str(d.get("content", "")),
        model=str(d.get("model", "")),
        provider=str(d.get("provider", "")),
        input_tokens=int(d.get("inputTokens", 0)),
        output_tokens=int(d.get("outputTokens", 0)),
        cached_input_tokens=int(d.get("cachedInputTokens", 0)),
        cost_usd=float(d.get("costUsd", 0.0)),
        stop_reason=d.get("stopReason"),
        purpose=d.get("purpose"),
    )
