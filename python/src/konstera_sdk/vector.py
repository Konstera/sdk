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
    """RAG store — vector similarity search over text chunks.

    Namespace convention:

    - `agent:<instance-uuid>` — private to one agent instance (default when the
      agent uses its own identity as the namespace).
    - `shared:<name>` — shared across a tenant's agents. Use for cross-agent
      knowledge bases (product catalogue, policy docs).

    Example:
        >>> # Index policy docs once (e.g. in initialize())
        >>> await ctx.vector.upsert(
        ...     namespace="shared:policies",
        ...     content="Refunds within 30 days get a 100% refund.",
        ...     external_id="policy-refund-window",
        ...     metadata={"source": "handbook.pdf", "page": 7},
        ... )
        >>>
        >>> # Query at invocation time
        >>> hits = await ctx.vector.query(
        ...     namespace="shared:policies",
        ...     query_text="customer wants refund after 2 months",
        ...     top_k=3,
        ... )
        >>> for h in hits:
        ...     print(f"[{h.score:.2f}] {h.content}")
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
        """Upsert a chunk into the vector store.

        Args:
            namespace: `"agent:<uuid>"` for private storage or `"shared:<name>"`
                for cross-agent.
            content: The text to embed and store. Chunk size convention: ~500
                tokens — the kernel's embedder is tuned for that range.
            external_id: Caller-stable ID. If provided, a later upsert with
                the same `external_id` replaces the chunk (same vector slot).
                Essential for idempotent re-indexing.
            metadata: Arbitrary JSON-serialisable key/value pairs returned
                with each hit on query. Use for provenance (source URL, page,
                last-modified).

        Returns:
            The chunk's UUID (kernel-generated). Save it if you need to
            `delete()` later and don't have `external_id`.

        Example:
            >>> await ctx.vector.upsert(
            ...     namespace="shared:kb",
            ...     content="Return window is 30 days from delivery.",
            ...     external_id="kb-return-window",
            ...     metadata={"source": "handbook", "updated_at": "2026-10-01"},
            ... )
        """
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
            return str(json.loads(raw)["chunkId"])
        except (json.JSONDecodeError, KeyError, TypeError):
            return raw or ""

    async def query(
        self, namespace: str, query_text: str, *, top_k: int = 5
    ) -> list[VectorHit]:
        """Top-K nearest chunks by cosine similarity.

        Args:
            namespace: Same namespace that was used in `upsert()`.
            query_text: Natural-language query. The kernel embeds it the same
                way it embedded the chunks on upsert, then returns the top-K
                by cosine similarity.
            top_k: Number of hits to return. Defaults to 5. Higher K is more
                tokens for a downstream LLM; keep as small as the use case
                tolerates.

        Returns:
            List of `VectorHit` dataclasses (id, external_id, content, metadata,
            score). Ordered by descending score. Empty list on an empty or
            malformed kernel response.

        Example:
            >>> hits = await ctx.vector.query(
            ...     namespace="shared:kb", query_text="refund policy", top_k=3,
            ... )
            >>> # Feed to an LLM as context
            >>> ctx_text = "\\n\\n".join(f"- {h.content}" for h in hits)
            >>> result = await ctx.llm.complete(
            ...     prompt=f"Policy snippets:\\n{ctx_text}\\n\\nQ: ...",
            ...     purpose="narrator",
            ... )
        """
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
        """Delete a chunk by its `external_id`.

        Args:
            namespace: Same namespace used in the original `upsert()`.
            external_id: The caller-stable ID passed to `upsert()`.
                Idempotent — deleting a missing ID is a no-op.

        Example:
            >>> # Remove a stale policy entry
            >>> await ctx.vector.delete("shared:kb", "kb-return-window-v1")
        """
        await self._mcp.call_tool_for_result(
            "vector_delete",
            {
                "callerInstanceId": self._instance,
                "namespace": namespace,
                "externalId": external_id,
            },
        )
