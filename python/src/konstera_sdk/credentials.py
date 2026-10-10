"""CredentialsService — tenant-scoped secret resolver.

Kernel returns the resolved value; SDK forwards it. Never log the value
your agent code receives from `ctx.credentials.get(...)`.

M8: kernel resolves tenant from the caller instance UUID that the SDK
passes on every call. Agent authors don't see this — the constructor
captures the instance ID and the SDK injects it automatically.
"""
from __future__ import annotations

from ._mcp import KernelMcpClient


class CredentialsService:
    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def get(self, key: str) -> str:
        """Resolve a credential by key. Raises if the key doesn't exist.
        Never log the returned value or include it in prompts."""
        result = await self._mcp.call_tool_for_result(
            "credentials_get",
            {"callerInstanceId": self._instance, "key": key},
        )
        return str(result) if result is not None else ""
