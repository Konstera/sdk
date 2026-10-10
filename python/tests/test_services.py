"""Direct-run-mode tests for the M7a service surface.

These don't hit a live kernel — they exercise the SDK's shape and the
no-kernel fallback semantics. Integration tests against a running kernel
live in the smoke-test scripts, not here.
"""
from __future__ import annotations

import pytest

from konstera_sdk import AgentContext
from konstera_sdk._mcp import KernelMcpClient


@pytest.fixture
def ctx() -> AgentContext:
    """A context with no kernel MCP URL — services that require the
    kernel raise informatively; log-style services no-op."""
    return AgentContext.from_env(KernelMcpClient(None))


async def test_context_exposes_all_m7a_services(ctx: AgentContext):
    assert ctx.log is not None
    assert ctx.llm is not None
    assert ctx.state is not None
    assert ctx.vector is not None
    assert ctx.credentials is not None
    assert ctx.cost is not None
    assert ctx.tool is not None
    assert ctx.agents is not None


async def test_state_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.state.get("some-key")


async def test_vector_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.vector.query("agent:foo", "hello")


async def test_credentials_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.credentials.get("SOME_KEY")


async def test_cost_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.cost.record(kind="tool", cost_usd=0.01)


async def test_tool_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.tool.list()


async def test_agents_invoke_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.agents.invoke("00000000-0000-0000-0000-000000000000", input="hi")


async def test_artifact_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.artifact.put(b"hello", content_type="text/plain")


async def test_log_still_noop_in_direct_run_mode(ctx: AgentContext):
    # Log calls tolerate a missing kernel (fire-and-forget with warning),
    # unlike state/vector/etc. which propagate the error.
    await ctx.log.info("this must not raise")


async def test_context_exposes_artifact_service_after_m7b(ctx: AgentContext):
    assert ctx.artifact is not None
    # Signature check — ensures we didn't accidentally break the SDK surface.
    assert hasattr(ctx.artifact, "put")
    assert hasattr(ctx.artifact, "get")
    assert hasattr(ctx.artifact, "head")
    assert hasattr(ctx.artifact, "list_by_uploader")


async def test_human_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.human.request(kind="test", tier="T3", summary="nope")


async def test_context_exposes_human_service_after_m7c(ctx: AgentContext):
    assert ctx.human is not None
    assert hasattr(ctx.human, "request")
    assert hasattr(ctx.human, "get")
    assert hasattr(ctx.human, "wait")
    assert hasattr(ctx.human, "list_pending")


def test_human_decision_helpers():
    # Pure-Python round-trip through _from_dict, no kernel needed.
    from konstera_sdk import HumanDecision
    from konstera_sdk.human import HumanService

    approved = HumanService._from_dict({
        "approvalId": "a", "kind": "k", "tier": "T3", "status": "approved",
        "summary": "s", "submitterInstanceId": "i", "options": ["approve"],
        "decision": "approve", "submittedAt": "now",
    })
    pending = HumanService._from_dict({
        "approvalId": "b", "kind": "k", "tier": "T1", "status": "pending",
        "summary": "s", "submitterInstanceId": "i", "options": ["approve", "reject"],
        "submittedAt": "now",
    })
    assert isinstance(approved, HumanDecision)
    assert approved.is_resolved
    assert approved.is_approved
    assert not pending.is_resolved
    assert not pending.is_approved


class _RecordingMcp:
    """Captures the tool call instead of reaching a kernel."""
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def call_tool_for_result(self, tool: str, args: dict):
        self.calls.append((tool, args))
        return '{"approvalId": "new", "status": "pending"}'


async def test_human_request_sends_parent_approval_id_only_when_given():
    # ADR-027: a redraft names the approval it replaces; older callers that
    # don't pass it send exactly the same arguments as before.
    from konstera_sdk.human import HumanService

    mcp = _RecordingMcp()
    human = HumanService(mcp, "inst-1")  # type: ignore[arg-type]
    await human.request(kind="k", tier="T1", summary="s")
    await human.request(kind="k", tier="T1", summary="s", parent_approval_id="parent-1")

    (tool1, first), (tool2, second) = mcp.calls
    assert tool1 == tool2 == "human_submit"
    assert "parentApprovalId" not in first
    assert second["parentApprovalId"] == "parent-1"


async def test_rule_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.rule.get("some-key")


async def test_connector_requires_kernel(ctx: AgentContext):
    with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL"):
        await ctx.connector.list()


async def test_context_exposes_connector_service(ctx: AgentContext):
    assert ctx.connector is not None
    assert hasattr(ctx.connector, "list")
    assert hasattr(ctx.connector, "call")


async def test_context_exposes_rule_service_after_m7d(ctx: AgentContext):
    assert ctx.rule is not None
    assert hasattr(ctx.rule, "get")
    assert hasattr(ctx.rule, "get_by_id")
    assert hasattr(ctx.rule, "list")


def test_rule_parse_dict():
    from konstera_sdk.rule import Rule, RuleService
    r = RuleService._parse_dict({
        "ruleId": "abc", "ruleKey": "prepayment-classification", "version": 1,
        "content": {"threshold_usd": 5000, "min_service_months": 3},
        "description": "seed",
        "effectiveFrom": "2026-01-01T00:00:00Z",
        "proposedAt": "2026-01-01T00:00:00Z",
    })
    assert isinstance(r, Rule)
    assert r.rule_id == "abc"
    assert r.version == 1
    assert r.content["threshold_usd"] == 5000
