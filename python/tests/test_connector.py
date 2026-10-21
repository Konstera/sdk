"""ConnectorService (ADR-009) — tenant-configured connection invocation.

Covers list() + call() with happy path, empty responses, nested args.
"""
from __future__ import annotations

import json
from typing import Any

from konstera_sdk.connector import ConnectorGrant, ConnectorService


class RecordingMcp:
    def __init__(self, response: str = ""):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.response = response

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self.response


class TestList:
    async def test_returns_grants_from_kernel(self):
        grants = [
            {
                "alias": "shopify_uk",
                "connectorTypeKey": "shopify",
                "connectionId": "conn-1",
                "scope": {"shop": "demo.myshopify.com", "readonly": True},
            },
            {
                "alias": "pg_analytics",
                "connectorTypeKey": "postgres",
                "connectionId": "conn-2",
                "scope": {},
            },
        ]
        mcp = RecordingMcp(response=json.dumps(grants))
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await conn.list()

        assert len(result) == 2
        assert isinstance(result[0], ConnectorGrant)
        assert result[0].alias == "shopify_uk"
        assert result[0].connector_type_key == "shopify"
        assert result[0].scope == {"shop": "demo.myshopify.com", "readonly": True}
        assert result[1].scope == {}

    async def test_returns_empty_list_when_no_grants(self):
        mcp = RecordingMcp(response="")
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await conn.list() == []

    async def test_sends_caller_instance_id(self):
        mcp = RecordingMcp(response="[]")
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]
        await conn.list()
        assert mcp.calls == [("connector_list", {"callerInstanceId": "inst-1"})]

    async def test_tolerates_partial_grant_shapes(self):
        """Future kernel versions might add fields; missing ones should
        default rather than crash the agent."""
        grants = [{"alias": "x"}]
        mcp = RecordingMcp(response=json.dumps(grants))
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]
        result = await conn.list()
        assert result[0].alias == "x"
        assert result[0].connector_type_key == ""
        assert result[0].connection_id == ""
        assert result[0].scope == {}


class TestCall:
    async def test_invokes_with_alias_method_and_args(self):
        mcp = RecordingMcp(response='{"rows": [{"id": 1}, {"id": 2}]}')
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await conn.call(
            "pg_analytics", "query", {"sql": "SELECT * FROM users LIMIT 2"}
        )

        assert result == {"rows": [{"id": 1}, {"id": 2}]}
        tool, args = mcp.calls[0]
        assert tool == "connector_call"
        assert args["callerInstanceId"] == "inst-1"
        assert args["alias"] == "pg_analytics"
        assert args["method"] == "query"
        assert json.loads(args["argsJson"]) == {"sql": "SELECT * FROM users LIMIT 2"}

    async def test_call_with_no_args_sends_empty_json(self):
        mcp = RecordingMcp(response="{}")
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]
        await conn.call("shopify_uk", "list_products")
        assert mcp.calls[0][1]["argsJson"] == "{}"

    async def test_call_with_none_args_sends_empty_json(self):
        mcp = RecordingMcp(response="{}")
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]
        await conn.call("x", "y", args=None)
        assert mcp.calls[0][1]["argsJson"] == "{}"

    async def test_returns_empty_dict_for_empty_response(self):
        """Different from capability.call which returns None — connector.call
        is more structured and empty-dict is a saner default."""
        mcp = RecordingMcp(response="")
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await conn.call("x", "y") == {}

    async def test_returns_list_response(self):
        """Connector methods can return lists directly (e.g. commercetools
        products.query), not just dicts."""
        mcp = RecordingMcp(response='[{"id": 1}, {"id": 2}]')
        conn = ConnectorService(mcp, "inst-1")  # type: ignore[arg-type]
        result = await conn.call("ct", "products.query")
        assert result == [{"id": 1}, {"id": 2}]
