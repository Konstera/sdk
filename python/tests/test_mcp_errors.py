"""Kernel tool errors must reach the agent as exceptions (finding F-13).

MCP reports a failed tool call as a normal CallToolResult with isError=true.
Before the fix the SDK returned the error text as data, so a failed
capability call looked like an empty result to the agent.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from konstera_sdk import CapabilityError, CapabilityUnbound
from konstera_sdk._mcp import tool_result_text
from konstera_sdk.capability import CapabilityService, CapabilityUpstreamFailed


def _result(text: str | None, is_error: bool) -> SimpleNamespace:
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    return SimpleNamespace(content=content, is_error=is_error)


def test_successful_result_returns_text():
    assert tool_result_text("x", _result('[{"orderId":"1"}]', False)) == '[{"orderId":"1"}]'
    assert tool_result_text("x", _result(None, False)) is None


def test_error_result_raises_with_the_kernel_message():
    with pytest.raises(
        RuntimeError, match=r"\[UpstreamFailed\] orders/search failed \(500\)"
    ):
        tool_result_text(
            "capability_call",
            _result("[UpstreamFailed] orders/search failed (500)", True),
        )


def test_error_result_without_text_still_raises():
    with pytest.raises(RuntimeError, match="capability_call"):
        tool_result_text("capability_call", _result(None, True))


class _FailingMcp:
    def __init__(self, message: str):
        self._message = message

    async def call_tool_for_result(self, name, args):
        raise RuntimeError(self._message)


@pytest.mark.parametrize("message, expected", [
    ("[UpstreamFailed] BetterCommerce POST … failed (500)", CapabilityUpstreamFailed),
    ("[Unbound] Agent has no binding for 'orders.lookup_by_id'", CapabilityUnbound),
    ("An error occurred invoking 'capability_call'.", CapabilityError),
])
async def test_capability_call_raises_typed_errors(message, expected):
    svc = CapabilityService(_FailingMcp(message), "agent-1")
    with pytest.raises(expected):
        await svc.call("orders.lookup_by_email", email="a@b.com")


class _RecordingMcp:
    def __init__(self):
        self.calls = []

    async def call_tool_for_result(self, name, args):
        self.calls.append((name, args))
        return '{"executionCount": 3}'


async def test_capability_call_accepts_an_argument_called_name():
    # db.object.definition / db.proc.stats take {name}: the capability name is positional-only.
    mcp = _RecordingMcp()
    svc = CapabilityService(mcp, "agent-1")
    assert await svc.call("db.proc.stats", name="dbo.procDWGetProductsToSync") == {
        "executionCount": 3
    }
    tool, args = mcp.calls[0]
    assert tool == "capability_call" and args["name"] == "db.proc.stats"
    assert args["argsJson"] == '{"name": "dbo.procDWGetProductsToSync"}'


async def test_capability_call_sends_the_current_invocation_id():
    # ADR-023: the kernel uses it to let a human-authored call act for the approver.
    from konstera_sdk._invocation_context import enter_invocation

    mcp = _RecordingMcp()
    svc = CapabilityService(mcp, "agent-1")
    with enter_invocation("3f2504e0-4f89-11d3-9a0c-0305e82c3301"):
        await svc.call("tickets.reply", ticketId="7", body="Hi")
    _, args = mcp.calls[0]
    assert args["invocationId"] == "3f2504e0-4f89-11d3-9a0c-0305e82c3301"


async def test_capability_call_outside_an_invocation_sends_no_invocation_id():
    mcp = _RecordingMcp()
    svc = CapabilityService(mcp, "agent-1")
    await svc.call("tickets.reply", ticketId="7", body="Hi")
    _, args = mcp.calls[0]
    assert "invocationId" not in args
