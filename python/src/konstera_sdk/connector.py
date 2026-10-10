"""ConnectorService — agent-facing view of the connector framework (ADR-009).

Two operations:
  - list()          → what am I granted?
  - call(alias, method, args) → invoke a granted connection

Zero connection setup on the agent side — the tenant configures the
connection once in the portal, an admin grants this agent access, and
the agent calls by alias.

Ungranted call raises RuntimeError (kernel returns InvalidOperationException
which the MCP client surfaces as an error result).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ._mcp import KernelMcpClient


@dataclass(slots=True, frozen=True)
class ConnectorGrant:
    """One entry from ConnectorService.list — the agent's granted connections.
    `alias` is what you pass to call()."""
    alias: str
    connector_type_key: str
    connection_id: str
    scope: dict[str, Any]


class ConnectorService:
    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def list(self) -> list[ConnectorGrant]:
        """The connections this agent has been granted."""
        raw = await self._mcp.call_tool_for_result(
            "connector_list", {"callerInstanceId": self._instance}
        )
        items = json.loads(raw) if raw else []
        return [
            ConnectorGrant(
                alias=str(x.get("alias", "")),
                connector_type_key=str(x.get("connectorTypeKey", "")),
                connection_id=str(x.get("connectionId", "")),
                scope=x.get("scope") or {},
            )
            for x in items
        ]

    async def call(
        self, alias: str, method: str, args: dict[str, Any] | None = None
    ) -> Any:
        """Invoke a granted connection.

        `alias` is the tenant-configured name (e.g. 'shopify_uk', 'pg_analytics').
        `method` is connector-type-specific (postgres: 'query'/'list_tables';
        rest: 'get'/'post'; commercetools: 'products.query'; etc).
        `args` is a JSON-serialisable dict.

        Returns whatever the connector method returns — cast to the shape you
        expect (typically a dict or a list of dicts)."""
        args_json = json.dumps(args or {})
        raw = await self._mcp.call_tool_for_result(
            "connector_call",
            {
                "callerInstanceId": self._instance,
                "alias": alias,
                "method": method,
                "argsJson": args_json,
            },
        )
        if not raw:
            return {}
        return json.loads(raw)
