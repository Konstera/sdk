"""The `run()` entry point — hosts the agent as an HTTP server."""
from __future__ import annotations

import contextlib
import logging
import os
import signal
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ._invocation_context import enter_invocation
from ._mcp import KernelMcpClient
from .agent import Agent
from .context import AgentContext
from .types import AgentRequest, AgentResponse

logger = logging.getLogger("konstera_sdk.runtime")


def build_app(agent: Agent, ctx: AgentContext) -> Starlette:
    """Build the Starlette app that hosts `agent` under `ctx`.

    Factored out from `run()` so tests can exercise the HTTP surface
    (/health, /describe, /invoke) with a Starlette TestClient without
    needing uvicorn in-the-loop. Production callers go through `run()`.

    Routes:
      - GET  /health   → `{"status": "ok", "agent": ..., "version": ...}`
      - GET  /describe → agent identity + capabilities (M15: tool list)
      - POST /invoke   → deserialises body → AgentRequest, runs
        `agent.handle(req, ctx)` under `enter_invocation(req.invocation_id)`,
        serialises the response. Exceptions produce HTTP 500 with
        `{"error": {"type": "...", "message": "..."}}` and are logged.
    """
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "agent": ctx.agent_id, "version": ctx.agent_version})

    async def describe(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "id": ctx.agent_id,
                "version": ctx.agent_version,
                "capabilities": ["kernel-mcp-callback"],
                "tools": [],
            }
        )

    async def invoke(request: Request) -> JSONResponse:
        body: dict[str, Any] = await request.json()
        req = AgentRequest(
            invocation_id=str(body.get("invocationId", "missing")),
            input=str(body.get("input", "")),
            payload=body.get("payload"),
            config=body.get("config") or {},
        )
        # Enter the ambient invocation scope so ctx.log.* and ctx.llm.*
        # (and any future correlation-aware service) auto-inject the
        # invocation_id without the agent having to thread it manually.
        try:
            with enter_invocation(req.invocation_id):
                resp = await agent.handle(req, ctx)
        except Exception as ex:
            logger.exception("agent.handle failed for invocation %s", req.invocation_id)
            return JSONResponse(
                {"error": {"type": type(ex).__name__, "message": str(ex)}},
                status_code=500,
            )
        return JSONResponse(_serialize_response(resp))

    async def lifespan(_app: Starlette):  # type: ignore[no-untyped-def]
        # Starlette's lifespan protocol expects an async generator; no clean
        # way to annotate the yield-type without pulling in Starlette internals.
        await agent.initialize(ctx)
        try:
            yield
        finally:
            with contextlib.suppress(Exception):
                await agent.shutdown(ctx)

    return Starlette(
        debug=False,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/describe", describe, methods=["GET"]),
            Route("/invoke", invoke, methods=["POST"]),
        ],
        lifespan=lifespan,
    )


def run(agent: Agent, port: int = 8080) -> None:
    """Host `agent` as an HTTP server. Blocks until `SIGTERM` or `SIGINT`.

    Reads the following env vars set by the kernel's `ContainerAgentHost` at
    container-create time:

    - `KONSTERA_KERNEL_MCP_URL` — kernel's MCP callback endpoint. Unset in
      direct-run / local-dev mode; kernel-callback services become no-ops.
    - `KONSTERA_AGENT_INSTANCE_ID` — this instance's UUID.
    - `KONSTERA_TENANT_ID` — tenant UUID.
    - `KONSTERA_AGENT_ID` — the manifest-declared id (e.g. `io.konstera.hello`).
    - `KONSTERA_AGENT_VERSION` — the manifest-declared version.
    - `KONSTERA_LOG_LEVEL` — Python log level (default `INFO`).

    Serves three HTTP endpoints:

    - `GET /health` — liveness check. Returns `{status, agent, version}`.
    - `GET /describe` — agent metadata. Returns `{id, version, capabilities, tools}`.
    - `POST /invoke` — accepts `{invocationId, input, payload, config}`,
      runs `agent.handle(req, ctx)` under the ambient invocation scope,
      returns `{content, structured, toolCalls}`. Exceptions in `handle`
      produce HTTP 500 with `{"error": {"type", "message"}}` and are logged.

    Lifecycle: `agent.initialize(ctx)` fires once on startup;
    `agent.shutdown(ctx)` fires on graceful stop. Exceptions in `shutdown`
    are swallowed to not block container exit.

    Args:
        agent: An instance of your Agent subclass.
        port: HTTP listen port. Defaults to 8080 (matches the Konstera
            container contract — the kernel maps this internally).

    Example:
        >>> from konstera_sdk import Agent, AgentContext, AgentRequest, AgentResponse, run
        >>>
        >>> class HelloAgent(Agent):
        ...     async def handle(
        ...         self, req: AgentRequest, ctx: AgentContext
        ...     ) -> AgentResponse:
        ...         return AgentResponse(content=f"Hello, {req.input}!")
        >>>
        >>> if __name__ == "__main__":
        ...     run(HelloAgent())
    """
    logging.basicConfig(
        level=os.getenv("KONSTERA_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    mcp_url = os.getenv("KONSTERA_KERNEL_MCP_URL")
    mcp = KernelMcpClient(mcp_url)
    ctx = AgentContext.from_env(mcp)

    if mcp.enabled:
        logger.info("Kernel MCP URL: %s", mcp_url)
    else:
        logger.warning(
            "KONSTERA_KERNEL_MCP_URL not set — kernel callbacks disabled (direct-run mode)."
        )

    app = build_app(agent, ctx)

    # Uvicorn manages the SIGINT/SIGTERM handling; nothing extra to wire here.
    # `access_log=False` — the kernel's invocation record is the audit trail;
    # per-request access logs would double-count.
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", access_log=False)


def _serialize_response(resp: AgentResponse) -> dict[str, Any]:
    """Serialise an AgentResponse to the /invoke HTTP body shape the kernel expects."""
    return {
        "content": resp.content,
        "structured": resp.structured,
        "toolCalls": resp.tool_calls,
        # kernelMcpStatus is filled by the kernel side — we don't set it from here.
    }


__all__ = ["build_app", "run"]

# Signal handling note: uvicorn.run() installs its own SIGTERM/SIGINT handlers
# and drives the lifespan protocol on shutdown. We deliberately don't add our
# own signal.signal() calls — they'd conflict. Any SIGKILL is outside our
# control (as it should be).
_ = signal  # keep the import for readers grepping for signal handling
