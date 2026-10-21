"""ToolService — call platform-provided tools (datetime_now, hash_sha256, etc.).

The service is simple — list + call — but it's the surface agent authors
hit most often for utility operations, so test coverage matters for the
LLM-authorship bar.
"""
from __future__ import annotations

import json
from typing import Any

from konstera_sdk.tool import ToolService


class RecordingMcp:
    def __init__(self, responses: dict[str, str] | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses = responses or {}

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self.responses.get(tool, "")


class TestToolServiceList:
    async def test_list_returns_tool_descriptors(self):
        descriptors = [
            {"name": "datetime_now", "description": "Current UTC datetime."},
            {"name": "hash_sha256", "description": "SHA-256 hash."},
        ]
        mcp = RecordingMcp(responses={"tool_list": json.dumps(descriptors)})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        result = await tools.list()

        assert result == descriptors
        assert mcp.calls == [("tool_list", {})]

    async def test_list_returns_empty_list_when_no_tools(self):
        mcp = RecordingMcp(responses={"tool_list": ""})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        assert await tools.list() == []

    async def test_list_tolerates_malformed_response(self):
        mcp = RecordingMcp(responses={"tool_list": "<not-json>"})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        assert await tools.list() == []


class TestToolServiceCall:
    async def test_call_serialises_kwargs_to_argsjson(self):
        mcp = RecordingMcp(responses={"tool_call": '"2026-10-21T12:00:00Z"'})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        result = await tools.call("datetime_now", tz="UTC", format="iso8601")

        assert result == "2026-10-21T12:00:00Z"
        assert mcp.calls[0][0] == "tool_call"
        args = mcp.calls[0][1]
        assert args["name"] == "datetime_now"
        assert json.loads(args["argsJson"]) == {"tz": "UTC", "format": "iso8601"}

    async def test_call_with_no_kwargs_sends_empty_args(self):
        mcp = RecordingMcp(responses={"tool_call": '"ok"'})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        result = await tools.call("ping")

        assert result == "ok"
        assert json.loads(mcp.calls[0][1]["argsJson"]) == {}

    async def test_call_deserialises_structured_result(self):
        payload = {"hash": "abc123", "algorithm": "sha256", "input_length": 42}
        mcp = RecordingMcp(responses={"tool_call": json.dumps(payload)})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        result = await tools.call("hash_sha256", data="hello")

        assert result == payload

    async def test_call_returns_none_for_empty_response(self):
        mcp = RecordingMcp(responses={"tool_call": ""})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        assert await tools.call("some_tool", arg=1) is None

    async def test_call_returns_raw_for_non_json_response(self):
        """Legacy or non-structured tools might return plain strings;
        tolerate rather than crash the agent."""
        mcp = RecordingMcp(responses={"tool_call": "plain-string-result"})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        assert await tools.call("echo", msg="hi") == "plain-string-result"

    async def test_call_serialises_non_json_args_via_default_str(self):
        """datetime, Decimal, and similar non-JSON types pass through via
        the default=str fallback."""
        import datetime as dt

        mcp = RecordingMcp(responses={"tool_call": "null"})
        tools = ToolService(mcp)  # type: ignore[arg-type]

        await tools.call("needs_date", when=dt.date(2026, 10, 21))

        args_json = mcp.calls[0][1]["argsJson"]
        assert "2026-10-21" in args_json
