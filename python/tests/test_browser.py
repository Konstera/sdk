"""BrowserService — kernel-hosted browser sessions.

Covers argument mapping per MCP tool, JSON decoding, screenshot base64
decoding, context-manager close, error propagation and direct-run mode.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import pytest

import konstera_sdk
from konstera_sdk import AgentContext, BrowserService, BrowserSession
from konstera_sdk._mcp import KernelMcpClient

OPEN_RESPONSE = json.dumps(
    {
        "sessionId": "sess-1",
        "connection": {
            "alias": "amazon_uk",
            "type": "amazon_account",
            "config": {"domain": "amazon.co.uk"},
        },
    }
)


class RecordingMcp:
    """Fake kernel MCP client. `responses` maps tool name -> raw result text;
    `errors` maps tool name -> exception to raise."""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        errors: dict[str, Exception] | None = None,
    ):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses = {"browser_open_session": OPEN_RESPONSE, **(responses or {})}
        self.errors = errors or {}

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        if tool in self.errors:
            raise self.errors[tool]
        return self.responses.get(tool, "{}")

    def last(self) -> tuple[str, dict[str, Any]]:
        return self.calls[-1]


async def open_session(mcp: RecordingMcp) -> BrowserSession:
    return await BrowserService(mcp, "inst-1").open_session("amazon_uk")  # type: ignore[arg-type]


BASE = {"callerInstanceId": "inst-1", "sessionId": "sess-1"}


class TestOpenSession:
    async def test_sends_alias_and_instance(self):
        mcp = RecordingMcp()
        await open_session(mcp)
        assert mcp.calls == [
            (
                "browser_open_session",
                {"callerInstanceId": "inst-1", "connectionAlias": "amazon_uk"},
            )
        ]

    async def test_decodes_session_and_connection(self):
        session = await open_session(RecordingMcp())
        assert isinstance(session, BrowserSession)
        assert session.session_id == "sess-1"
        assert session.connection == {
            "alias": "amazon_uk",
            "type": "amazon_account",
            "config": {"domain": "amazon.co.uk"},
        }

    async def test_tolerates_empty_response(self):
        session = await open_session(RecordingMcp({"browser_open_session": ""}))
        assert session.session_id == ""
        assert session.connection == {}

    async def test_error_propagates(self):
        mcp = RecordingMcp(errors={"browser_open_session": RuntimeError("[NotGranted] no")})
        with pytest.raises(RuntimeError, match="NotGranted"):
            await open_session(mcp)


class TestToolMapping:
    async def test_navigate(self):
        mcp = RecordingMcp({"browser_navigate": '{"url": "https://x/y", "title": "Y"}'})
        s = await open_session(mcp)
        assert await s.navigate("https://x") == {"url": "https://x/y", "title": "Y"}
        assert mcp.last() == ("browser_navigate", {**BASE, "url": "https://x", "waitUntil": "load"})
        await s.navigate("https://x", wait_until="networkidle")
        assert mcp.last()[1]["waitUntil"] == "networkidle"

    async def test_click(self):
        mcp = RecordingMcp()
        s = await open_session(mcp)
        assert await s.click("#go") is None
        assert mcp.last() == ("browser_click", {**BASE, "selector": "#go", "timeoutSeconds": 15})
        await s.click("#go", timeout_seconds=3)
        assert mcp.last()[1]["timeoutSeconds"] == 3

    async def test_type(self):
        mcp = RecordingMcp()
        s = await open_session(mcp)
        assert await s.type("#q", "hello") is None
        assert mcp.last() == (
            "browser_type",
            {**BASE, "selector": "#q", "text": "hello", "timeoutSeconds": 15},
        )

    async def test_type_secret_sends_field_name_not_value(self):
        mcp = RecordingMcp()
        s = await open_session(mcp)
        assert await s.type_secret("#ap_password", "password") is None
        assert mcp.last() == (
            "browser_type_secret",
            {**BASE, "selector": "#ap_password", "secretField": "password"},
        )

    async def test_wait_for_omits_unset_conditions(self):
        mcp = RecordingMcp({"browser_wait_for": '{"matched": true, "url": "https://x"}'})
        s = await open_session(mcp)
        assert await s.wait_for(selector="#orders") == {"matched": True, "url": "https://x"}
        assert mcp.last() == (
            "browser_wait_for",
            {**BASE, "selector": "#orders", "timeoutSeconds": 30},
        )
        await s.wait_for(url_contains="order-history", timeout_seconds=5)
        assert mcp.last()[1] == {**BASE, "urlContains": "order-history", "timeoutSeconds": 5}

    async def test_exists(self):
        mcp = RecordingMcp({"browser_exists": '{"exists": true, "count": 3}'})
        s = await open_session(mcp)
        assert await s.exists(".card") == {"exists": True, "count": 3}
        assert mcp.last() == ("browser_exists", {**BASE, "selector": ".card"})

    async def test_text(self):
        mcp = RecordingMcp({"browser_text": '{"text": "Order #1"}'})
        s = await open_session(mcp)
        assert await s.text("h1") == "Order #1"
        assert mcp.last() == ("browser_text", {**BASE, "selector": "h1"})

    async def test_text_none_when_no_match(self):
        s = await open_session(RecordingMcp({"browser_text": '{"text": null}'}))
        assert await s.text("h1") is None

    async def test_extract_serialises_fields_json(self):
        rows = [{"id": "1", "items": ["a", "b"]}, {"id": "2", "items": []}]
        mcp = RecordingMcp({"browser_extract": json.dumps({"rows": rows})})
        s = await open_session(mcp)
        fields = {"id": {"selector": ".id"}, "items": {"selector": ".item", "all": True}}
        assert await s.extract(".order", fields) == rows
        tool, args = mcp.last()
        assert tool == "browser_extract"
        assert args["rowSelector"] == ".order"
        assert json.loads(args["fieldsJson"]) == fields
        assert set(args) == {"callerInstanceId", "sessionId", "rowSelector", "fieldsJson"}

    async def test_extract_empty_rows(self):
        s = await open_session(RecordingMcp({"browser_extract": '{"rows": null}'}))
        assert await s.extract(".order", {}) == []

    async def test_screenshot_decodes_base64(self):
        png = b"\x89PNG\r\n\x1a\nfake"
        mcp = RecordingMcp(
            {"browser_screenshot": json.dumps({"pngBase64": base64.b64encode(png).decode()})}
        )
        s = await open_session(mcp)
        assert await s.screenshot("after-login") == png
        assert mcp.last() == ("browser_screenshot", {**BASE, "label": "after-login"})

    async def test_screenshot_empty(self):
        s = await open_session(RecordingMcp({"browser_screenshot": "{}"}))
        assert await s.screenshot("x") == b""

    async def test_handoff_to_human(self):
        mcp = RecordingMcp({"browser_handoff_to_human": '{"resolved": true, "url": "https://o"}'})
        s = await open_session(mcp)
        result = await s.handoff_to_human("CAPTCHA shown", until_url_contains="order-history")
        assert result == {"resolved": True, "url": "https://o"}
        assert mcp.last() == (
            "browser_handoff_to_human",
            {
                **BASE,
                "reason": "CAPTCHA shown",
                "untilUrlContains": "order-history",
                "timeoutSeconds": 300,
            },
        )
        await s.handoff_to_human("OTP", until_selector="#orders", timeout_seconds=60)
        assert mcp.last()[1] == {
            **BASE,
            "reason": "OTP",
            "untilSelector": "#orders",
            "timeoutSeconds": 60,
        }

    async def test_non_object_response_decodes_to_empty(self):
        s = await open_session(RecordingMcp({"browser_exists": "[1, 2]"}))
        assert await s.exists("x") == {}

    async def test_close(self):
        mcp = RecordingMcp()
        s = await open_session(mcp)
        assert await s.close() is None
        assert mcp.last() == ("browser_close_session", BASE)


class TestLifecycle:
    async def test_context_manager_closes(self):
        mcp = RecordingMcp()
        session = await open_session(mcp)
        async with session as s:
            assert s is session
            await s.click("#a")
        assert [c[0] for c in mcp.calls] == [
            "browser_open_session",
            "browser_click",
            "browser_close_session",
        ]

    async def test_async_with_await_open_session(self):
        mcp = RecordingMcp()
        service = BrowserService(mcp, "inst-1")  # type: ignore[arg-type]
        async with await service.open_session("amazon_uk") as s:
            await s.navigate("https://x")
        assert mcp.last()[0] == "browser_close_session"

    async def test_context_manager_closes_on_error_and_keeps_original(self):
        mcp = RecordingMcp(errors={"browser_close_session": RuntimeError("close failed")})
        session = await open_session(mcp)
        with pytest.raises(ValueError, match="boom"):
            async with session:
                raise ValueError("boom")
        assert mcp.last()[0] == "browser_close_session"

    async def test_close_error_propagates_without_body_error(self):
        mcp = RecordingMcp(errors={"browser_close_session": RuntimeError("close failed")})
        session = await open_session(mcp)
        with pytest.raises(RuntimeError, match="close failed"):
            async with session:
                pass

    async def test_close_is_idempotent(self):
        mcp = RecordingMcp()
        s = await open_session(mcp)
        await s.close()
        await s.close()
        async with s:
            pass
        assert [c[0] for c in mcp.calls].count("browser_close_session") == 1

    async def test_calls_after_close_raise(self):
        mcp = RecordingMcp()
        s = await open_session(mcp)
        await s.close()
        with pytest.raises(RuntimeError, match="closed"):
            await s.click("#a")

    async def test_tool_error_propagates(self):
        mcp = RecordingMcp(errors={"browser_click": RuntimeError("[Timeout] #a not found")})
        s = await open_session(mcp)
        with pytest.raises(RuntimeError, match="Timeout"):
            await s.click("#a")


class TestWiring:
    def test_exported(self):
        assert "BrowserService" in konstera_sdk.__all__
        assert "BrowserSession" in konstera_sdk.__all__

    def test_context_exposes_browser(self):
        ctx = AgentContext.from_env(KernelMcpClient(None))
        assert isinstance(ctx.browser, BrowserService)

    async def test_direct_run_mode_raises_clear_error(self):
        ctx = AgentContext.from_env(KernelMcpClient(None))
        with pytest.raises(RuntimeError, match="KONSTERA_KERNEL_MCP_URL is unset"):
            await ctx.browser.open_session("amazon_uk")
