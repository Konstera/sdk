"""Tests for _mcp.py — the transport wrapper over the mcp SDK's ClientSession.

Covers:
- `tool_result_text()` — unwraps MCP CallToolResult to text, raises on isError
- `KernelMcpClient.enabled` — direct-run detection
- `call_tool()` — fire-and-forget semantics; logs on failure, never raises
- `call_tool_for_result()` — raises when URL unset (RuntimeError with
  actionable message)

Not covered here: real HTTP roundtrips to a kernel. Those are integration
concerns and need a live kernel; this file focuses on the SDK's own logic.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from konstera_sdk._mcp import KernelMcpClient, tool_result_text


class TestKernelMcpClientEnabled:
    def test_enabled_true_when_url_set(self):
        c = KernelMcpClient("http://localhost:8080/mcp")
        assert c.enabled is True

    def test_enabled_false_when_url_none(self):
        c = KernelMcpClient(None)
        assert c.enabled is False

    def test_enabled_false_when_url_empty_string(self):
        c = KernelMcpClient("")
        assert c.enabled is False


class TestCallToolDirectRun:
    """call_tool is fire-and-forget — in direct-run mode it must silently
    skip (debug-log only, no raise, no warning spam)."""

    async def test_direct_run_mode_silently_skips(self, caplog):
        c = KernelMcpClient(None)
        with caplog.at_level(logging.DEBUG, logger="konstera_sdk.mcp"):
            await c.call_tool("log_info", {"message": "hi"})
        # No exception. Debug line emitted for debugging but not visible at INFO.
        assert any(
            "MCP disabled" in rec.message and "log_info" in rec.message
            for rec in caplog.records
        )


class TestCallToolForResultDirectRun:
    """call_tool_for_result is NOT fire-and-forget — services like llm need
    the response. Direct-run mode raises RuntimeError with a clear message
    that tells the agent author what to do."""

    async def test_direct_run_raises_actionable_runtime_error(self):
        c = KernelMcpClient(None)
        with pytest.raises(RuntimeError) as exc_info:
            await c.call_tool_for_result("state_get", {"key": "x"})
        msg = str(exc_info.value)
        assert "KONSTERA_KERNEL_MCP_URL" in msg
        assert "state_get" in msg
        assert "direct-run mode" in msg


class TestToolResultText:
    """tool_result_text extracts the kernel's text response, raising when the
    MCP CallToolResult has isError=true. This is the single choke point that
    kernel errors become Python exceptions."""

    def test_extracts_text_from_single_content_block(self):
        result = SimpleNamespace(
            content=[SimpleNamespace(text="hello world")],
            is_error=False,
        )
        assert tool_result_text("some_tool", result) == "hello world"

    def test_concatenates_multiple_text_blocks(self):
        """Rare in practice but MCP allows it — the SDK should concatenate
        rather than silently dropping all-but-the-first block."""
        result = SimpleNamespace(
            content=[
                SimpleNamespace(text="part1 "),
                SimpleNamespace(text="part2"),
            ],
            is_error=False,
        )
        assert tool_result_text("some_tool", result) == "part1 part2"

    def test_ignores_content_blocks_without_text_attribute(self):
        """MCP may add image / resource blocks in future; be defensive."""
        result = SimpleNamespace(
            content=[
                SimpleNamespace(data="binary"),  # no .text
                SimpleNamespace(text="useful"),
            ],
            is_error=False,
        )
        assert tool_result_text("some_tool", result) == "useful"

    def test_returns_none_when_content_is_empty(self):
        result = SimpleNamespace(content=[], is_error=False)
        assert tool_result_text("some_tool", result) is None

    def test_returns_none_when_content_attr_missing(self):
        result = SimpleNamespace(is_error=False)
        assert tool_result_text("some_tool", result) is None

    def test_returns_none_when_content_is_none(self):
        result = SimpleNamespace(content=None, is_error=False)
        assert tool_result_text("some_tool", result) is None

    def test_raises_runtime_error_on_is_error_true(self):
        """When the kernel reports a tool failure (not a transport failure),
        the error text is surfaced as a RuntimeError. Loses nothing — the
        caller gets the exact kernel message."""
        result = SimpleNamespace(
            content=[SimpleNamespace(text="[Unbound] Agent has no binding for X")],
            is_error=True,
        )
        with pytest.raises(RuntimeError, match=r"Unbound.*binding for X"):
            tool_result_text("capability_call", result)

    def test_handles_camel_case_is_error_variant(self):
        """Early mcp library versions used `isError`; later versions used
        `is_error`. The SDK supports both — if the lib changes again we only
        update this file."""
        result = SimpleNamespace(
            content=[SimpleNamespace(text="failed")],
            isError=True,
        )
        with pytest.raises(RuntimeError, match="failed"):
            tool_result_text("some_tool", result)

    def test_raises_with_placeholder_when_error_has_no_text(self):
        """Defensive: a failed tool without any message still raises, with
        a 'without an error message' placeholder — never silent."""
        result = SimpleNamespace(content=[], is_error=True)
        with pytest.raises(RuntimeError, match="without an error message"):
            tool_result_text("mystery_tool", result)
