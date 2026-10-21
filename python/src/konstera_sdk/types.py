"""Request/response types agents receive and return."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class AgentRequest:
    """One invocation into the agent. Assembled by the SDK from the /invoke HTTP body.

    Frozen dataclass — safe to pass across async boundaries without defensive
    copying. All fields are immutable; the agent reads them and emits a new
    `AgentResponse`.

    Example:
        >>> # Inside Agent.handle:
        >>> async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        ...     user_text = req.input                       # e.g. "refund order 123"
        ...     order_id = req.payload.get("order_id")      # None if not provided
        ...     max_retries = req.config.get("max_retries", 3)
        ...     await ctx.log.info("processing", input=user_text)
        ...     return AgentResponse(content="OK")
    """

    invocation_id: str
    """Kernel-generated UUID for this invocation. Automatically propagated into
    the ambient scope so `ctx.log.*` / `ctx.llm.*` tag their events with it.
    Include it in your own log messages when debugging — it correlates
    everything the kernel recorded for this run."""

    input: str
    """The primary text input. Empty string is valid — the agent decides what to
    do (default behavior, polling with no payload, etc.)."""

    payload: dict[str, Any] | None = None
    """Optional structured payload. Set by:
        - Webhook invocations (verbatim JSON body)
        - Structured tool-call-style invocations from other agents
        - Portal-triggered invocations with form fields
    `None` for plain-text invocations where only `input` matters."""

    config: dict[str, Any] = field(default_factory=dict)
    """Per-agent-instance behaviour config. Shape declared by the manifest's
    `config` JSON Schema; operator sets values in the portal Instance-
    Configuration panel. Empty dict when unset; always safe to call
    `.get(key, default)` on."""


@dataclass(slots=True)
class AgentResponse:
    """What the agent returns from `handle()`. Serialised to the /invoke HTTP body.

    Mutable (not frozen) so helper SDK functions can append to `tool_calls`
    as the agent orchestrates LLM calls.

    Example:
        >>> # Simple text reply
        >>> return AgentResponse(content="Refund approved for order 123.")
        >>>
        >>> # Reply with structured data for downstream consumers
        >>> return AgentResponse(
        ...     content="Processed 42 tickets.",
        ...     structured={"processed": 42, "skipped": 3, "errors": []},
        ... )
    """

    content: str
    """The primary text response. Empty string is valid but discouraged —
    callers reading just `/invoke` responses see this as the result."""

    structured: dict[str, Any] | None = None
    """Optional structured response for agents that produce data, not chat.
    Must be JSON-serialisable."""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """LLM tool calls the agent made, for observability. Populated by SDK
    helpers (`ctx.llm.complete()` appends automatically). Not required when
    the agent didn't make LLM calls."""
