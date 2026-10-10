"""VectorService — thin wrapper around the kernel MCP `vector_*` tools.

M7a note: kernel uses a deterministic hash-based stub embedder. Upsert +
query round-trip correctly, but results are NOT semantically meaningful.
Real embeddings land with M10 (OpenAI text-embedding-3-small etc.).

M8: caller instance UUID injected on every call for tenant resolution.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ._mcp import KernelMcpClient


@dataclass(slots=True, frozen=True)
class VectorHit:
    id: str
    external_id: str | None
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class VectorService:
    """RAG store. Namespaces:
        agent:<instance-uuid>  — private to one agent instance
        shared:<name>          — shared across a tenant's agents
    """

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def upsert(
        self,
        namespace: str,
        content: str,
        *,
        external_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Upsert a chunk. If `external_id` is provided, subsequent upserts
        with the same external_id replace the chunk. Returns the chunk UUID."""
        args: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "namespace": namespace,
            "content": content,
        }
        if external_id is not None:
            args["externalId"] = external_id
        if metadata:
            args["metadataJson"] = json.dumps(metadata, default=str)
        raw = await self._mcp.call_tool_for_result("vector_upsert", args)
        try:
            return json.loads(raw)["chunkId"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return raw or ""

    async def query(
        self, namespace: str, query_text: str, *, top_k: int = 5
    ) -> list[VectorHit]:
        """Top-K nearest chunks by cosine similarity."""
        raw = await self._mcp.call_tool_for_result(
            "vector_query",
            {
                "callerInstanceId": self._instance,
                "namespace": namespace,
                "queryText": query_text,
                "topK": top_k,
            },
        )
        try:
            items = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []
        return [
            VectorHit(
                id=str(h.get("id", "")),
                external_id=h.get("externalId"),
                content=h.get("content", ""),
                metadata=h.get("metadata") or {},
                score=float(h.get("score", 0.0)),
            )
            for h in items
        ]

    async def delete(self, namespace: str, external_id: str) -> None:
        await self._mcp.call_tool_for_result(
            "vector_delete",
            {
                "callerInstanceId": self._instance,
                "namespace": namespace,
                "externalId": external_id,
            },
        )
