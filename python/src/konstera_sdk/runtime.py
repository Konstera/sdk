"""The `run()` entry point — hosts the agent as an HTTP server."""
from __future__ import annotations

import contextlib
import dataclasses
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


def run(agent: Agent, port: int = 8080) -> None:
    """Host `agent` as an HTTP server on `port`. Blocks until SIGTERM/SIGINT.

    Reads KONSTERA_KERNEL_MCP_URL + KONSTERA_AGENT_* env vars set by the
    kernel's ContainerAgentHost at container-create time. Runs fine in
    direct-run mode (env unset) — kernel-callback services become no-ops.
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
        except Exception as ex:  # noqa: BLE001
            logger.exception("agent.handle failed for invocation %s", req.invocation_id)
            return JSONResponse(
                {"error": {"type": type(ex).__name__, "message": str(ex)}},
                status_code=500,
            )
        return JSONResponse(_serialize_response(resp))

    async def lifespan(_app: Starlette):
        await agent.initialize(ctx)
        try:
            yield
        finally:
            with contextlib.suppress(Exception):
                await agent.shutdown(ctx)

    app = Starlette(
        debug=False,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/describe", describe, methods=["GET"]),
            Route("/invoke", invoke, methods=["POST"]),
        ],
        lifespan=lifespan,
    )

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


__all__ = ["run"]

# Signal handling note: uvicorn.run() installs its own SIGTERM/SIGINT handlers
# and drives the lifespan protocol on shutdown. We deliberately don't add our
# own signal.signal() calls — they'd conflict. Any SIGKILL is outside our
# control (as it should be).
_ = signal  # keep the import for readers grepping for signal handling
