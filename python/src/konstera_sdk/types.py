"""Request/response types agents receive and return."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class AgentRequest:
    """One invocation into the agent. Assembled by the SDK from the /invoke HTTP body."""

    invocation_id: str
    """Kernel-generated ID for this invocation. Include in logs / traces."""

    input: str
    """The primary text input. Empty string is valid — agent decides what to do."""

    payload: dict[str, Any] | None = None
    """Optional structured payload (from webhook body, structured tool call, etc.)."""

    config: dict[str, Any] = field(default_factory=dict)
    """Per-agent-instance behavior config (#190). Shape declared by the
    manifest's `config` JSON Schema; operator sets values in the portal
    Instance-Configuration panel. Empty dict when unset; always safe to
    call `.get(key, default)` on."""


@dataclass(slots=True)
class AgentResponse:
    """What the agent returns from `handle()`. Serialised to the /invoke HTTP body."""

    content: str
    """The primary text response. Empty string is valid but discouraged."""

    structured: dict[str, Any] | None = None
    """Optional structured response (for agents that produce data, not chat)."""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """LLM tool calls the agent made, for observability. Populated by SDK helpers."""
