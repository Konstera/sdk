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

    Example:
        >>> from konstera_sdk import Agent, AgentContext, AgentRequest, AgentResponse, run
        >>>
        >>> class HelloAgent(Agent):
        ...     async def handle(
        ...         self, req: AgentRequest, ctx: AgentContext
        ...     ) -> AgentResponse:
        ...         name = req.input.strip() or "world"
        ...         await ctx.log.info(f"Hello, {name}!")
        ...         return AgentResponse(content=f"Hello, {name}!")
        >>>
        >>> if __name__ == "__main__":
        ...     run(HelloAgent())
    """

    async def initialize(self, ctx: AgentContext) -> None:
        """One-time setup at container startup.

        Called once before the HTTP server starts accepting invocations. Use
        for loading models, warming caches, or opening long-lived connections
        the agent reuses across invocations.

        Default implementation is a no-op — override only if you need setup.

        Args:
            ctx: The ambient AgentContext. Identity and all kernel services
                are available here just as they are inside `handle()`.

        Example:
            >>> class CachedAgent(Agent):
            ...     async def initialize(self, ctx: AgentContext) -> None:
            ...         self.product_catalogue = await ctx.vector.query(
            ...             namespace="shared:products", query_text="*", top_k=1000
            ...         )
        """
        return None

    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        """Handle one invocation. **Required override.**

        Called once per inbound invocation (sync HTTP, async queue, cron,
        or webhook — all routed through `/invoke`). Must return an
        `AgentResponse`.

        Args:
            req: Input to this invocation. `req.input` is the primary text,
                `req.payload` carries structured data, `req.config` carries
                instance-level config set by the operator in the portal.
            ctx: Identity + kernel services (log, llm, state, …).

        Returns:
            `AgentResponse` with `content` (text), optional `structured`
            (dict), and optional `tool_calls` (observability trace).

        Raises:
            NotImplementedError: If the subclass forgets to override this.
            Any exception raised here propagates to the kernel, which
            records it as a failed invocation and returns HTTP 500 with
            `{"error": {"type": ..., "message": ...}}`.
        """
        raise NotImplementedError(
            "Subclass Agent and override `async def handle(self, req, ctx) -> AgentResponse`."
        )

    async def shutdown(self, ctx: AgentContext) -> None:
        """Graceful stop. Close connections, flush buffers here.

        Called on `SIGTERM` or `SIGINT` after the HTTP server stops accepting
        new requests. Default implementation is a no-op.

        Args:
            ctx: The ambient AgentContext.

        Example:
            >>> class StatefulAgent(Agent):
            ...     async def shutdown(self, ctx: AgentContext) -> None:
            ...         await self.db_pool.close()
        """
        return None
