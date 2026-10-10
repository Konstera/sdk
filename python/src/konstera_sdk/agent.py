"""Agent base class. Subclass, override `handle()`, done."""
from __future__ import annotations

from .context import AgentContext
from .types import AgentRequest, AgentResponse


class Agent:
    """Base class every Konstera Python agent extends.

    Override `handle()` (required). Optionally override `initialize()` for
    one-time setup and `shutdown()` for cleanup.

    The SDK's `run()` function wires this up to an HTTP server + MCP client,
    but the class itself has no coupling to the transport — this makes
    agents unit-testable without spinning up any infrastructure.
    """

    async def initialize(self, ctx: AgentContext) -> None:
        """Called once at container startup. Load models, warm caches, open
        long-lived connections here. Default: no-op."""
        return None

    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        """Called for every invocation. Must be overridden."""
        raise NotImplementedError(
            "Subclass Agent and override `async def handle(self, req, ctx) -> AgentResponse`."
        )

    async def shutdown(self, ctx: AgentContext) -> None:
        """Called on graceful stop. Close connections, flush buffers here.
        Default: no-op."""
        return None
