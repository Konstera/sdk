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
    """Agent-facing view of the connector framework (ADR-009).

    Agents never configure connections — the tenant admin configures each
    connection once in the portal (an API key, an OAuth grant) and grants
    this agent access. The agent calls by alias.

    Compare with `ctx.capability.*`: capabilities are canonical purpose-first
    names (`orders.lookup_by_email`) backed by one of many possible connectors.
    Connectors are the raw transport layer. Use `ctx.capability` for business
    logic; use `ctx.connector` only when you need vendor-specific behaviour
    the capability layer doesn't expose.

    Example:
        >>> # List what's been granted to this agent
        >>> grants = await ctx.connector.list()
        >>> for g in grants:
        ...     print(f"{g.alias} ({g.connector_type_key})")
        >>>
        >>> # Call a connector method
        >>> rows = await ctx.connector.call(
        ...     "pg_analytics", "query",
        ...     {"sql": "SELECT COUNT(*) FROM orders WHERE status='pending'"},
        ... )
    """

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def list(self) -> list[ConnectorGrant]:
        """List connections this agent has been granted.

        Returns:
            List of `ConnectorGrant` (alias, connector_type_key, connection_id,
            scope). Empty list if nothing is granted.

        Example:
            >>> for grant in await ctx.connector.list():
            ...     if grant.connector_type_key == "shopify":
            ...         await ctx.connector.call(grant.alias, "list_products")
        """
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

        Args:
            alias: Tenant-configured name (e.g. `"shopify_uk"`, `"pg_analytics"`).
                Matches a `ConnectorGrant.alias` from `list()`.
            method: Connector-type-specific operation. Examples:
                - `postgres`: `"query"`, `"list_tables"`
                - `rest`: `"get"`, `"post"`
                - `commercetools`: `"products.query"`
                - `shopify`: `"orders.list"`, `"products.update"`
            args: JSON-serialisable keyword arguments for the method. Omit
                or pass `None` for methods with no arguments.

        Returns:
            Whatever the connector method returns — typically a dict or list
            of dicts. Cast on your side to the shape you expect.
            Empty dict (`{}`) when the kernel returns an empty response.

        Raises:
            RuntimeError: If the agent has no grant for this alias (via the
                kernel's error path), or the connector method itself threw.

        Example:
            >>> # Postgres query
            >>> rows = await ctx.connector.call(
            ...     "pg_analytics", "query",
            ...     {"sql": "SELECT id, email FROM customers WHERE tier='vip'"},
            ... )
            >>>
            >>> # Shopify order update
            >>> await ctx.connector.call(
            ...     "shopify_uk", "orders.update",
            ...     {"id": "o-12345", "status": "fulfilled"},
            ... )
        """
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
