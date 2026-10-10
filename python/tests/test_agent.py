"""Smoke tests for the SDK. Run offline — no kernel or MCP endpoint required
(the KernelMcpClient falls back to no-op when KONSTERA_KERNEL_MCP_URL is unset).

Run: `pytest sdk/python/tests` (from repo root, after `pip install -e sdk/python[dev]`).
"""
from __future__ import annotations

import os

import pytest

from konstera_sdk import Agent, AgentContext, AgentRequest, AgentResponse
from konstera_sdk._mcp import KernelMcpClient


class EchoAgent(Agent):
    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        await ctx.log.info(f"echoing {req.input}", invocation=req.invocation_id)
        return AgentResponse(content=f"echo:{req.input}")


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Isolate tests from any Konstera env vars in the developer's shell."""
    for key in ("KONSTERA_KERNEL_MCP_URL", "KONSTERA_AGENT_INSTANCE_ID",
                "KONSTERA_AGENT_ID", "KONSTERA_AGENT_VERSION"):
        monkeypatch.delenv(key, raising=False)


async def test_direct_run_mode_log_is_noop():
    """In direct-run mode, log calls should not raise even without a kernel."""
    ctx = AgentContext.from_env(KernelMcpClient(None))
    await ctx.log.info("hello", key="value")
    await ctx.log.warn("warn")
    await ctx.log.error("err")


async def test_agent_handle_produces_response():
    agent = EchoAgent()
    ctx = AgentContext.from_env(KernelMcpClient(None))
    req = AgentRequest(invocation_id="test-1", input="hello")
    resp = await agent.handle(req, ctx)
    assert resp.content == "echo:hello"


async def test_context_uses_defaults_when_env_missing():
    ctx = AgentContext.from_env(KernelMcpClient(None))
    assert ctx.agent_id == "unknown-agent"
    assert ctx.agent_version == "0.0.0"
    assert ctx.instance_id == "unknown-instance"


async def test_context_reads_env_when_set(monkeypatch):
    monkeypatch.setenv("KONSTERA_AGENT_ID", "io.konstera.test")
    monkeypatch.setenv("KONSTERA_AGENT_VERSION", "9.9.9")
    monkeypatch.setenv("KONSTERA_AGENT_INSTANCE_ID", "abcd-1234")
    ctx = AgentContext.from_env(KernelMcpClient(os.getenv("KONSTERA_KERNEL_MCP_URL")))
    assert ctx.agent_id == "io.konstera.test"
    assert ctx.agent_version == "9.9.9"
    assert ctx.instance_id == "abcd-1234"


async def test_default_agent_handle_raises():
    ctx = AgentContext.from_env(KernelMcpClient(None))
    req = AgentRequest(invocation_id="x", input="y")
    with pytest.raises(NotImplementedError):
        await Agent().handle(req, ctx)


async def test_llm_requires_kernel_mcp_url():
    """LLM calls should fail loudly in direct-run mode — agent must handle it."""
    ctx = AgentContext.from_env(KernelMcpClient(None))
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.llm.complete(model="claude-sonnet-4-6", prompt="hi")
