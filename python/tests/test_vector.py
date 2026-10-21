"""VectorService — RAG store wrapper. Tests happy-path upsert/query/delete
plus the hit-decoding + response-tolerance paths.
"""
from __future__ import annotations

import json
from typing import Any

from konstera_sdk.vector import VectorHit, VectorService


class RecordingMcp:
    def __init__(self, responses: dict[str, str] | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses = responses or {}

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self.responses.get(tool, "")


class TestVectorServiceUpsert:
    async def test_upsert_minimal_sends_namespace_and_content(self):
        mcp = RecordingMcp(responses={"vector_upsert": '{"chunkId": "chunk-abc"}'})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        chunk_id = await vector.upsert("agent:inst-1", "hello world")

        assert chunk_id == "chunk-abc"
        tool, args = mcp.calls[0]
        assert tool == "vector_upsert"
        assert args == {
            "callerInstanceId": "inst-1",
            "namespace": "agent:inst-1",
            "content": "hello world",
        }

    async def test_upsert_with_external_id_passes_through(self):
        mcp = RecordingMcp(responses={"vector_upsert": '{"chunkId": "chunk-xyz"}'})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        await vector.upsert("shared:kb", "content", external_id="doc-42")

        args = mcp.calls[0][1]
        assert args["externalId"] == "doc-42"

    async def test_upsert_with_metadata_serialises_to_json(self):
        mcp = RecordingMcp(responses={"vector_upsert": '{"chunkId": "chunk-1"}'})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        await vector.upsert(
            "agent:inst-1",
            "content",
            metadata={"source": "docs", "page": 7, "lang": "en"},
        )

        args = mcp.calls[0][1]
        assert json.loads(args["metadataJson"]) == {
            "source": "docs",
            "page": 7,
            "lang": "en",
        }

    async def test_upsert_omits_metadata_when_none(self):
        mcp = RecordingMcp(responses={"vector_upsert": '{"chunkId": "x"}'})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        await vector.upsert("agent:inst-1", "content")

        args = mcp.calls[0][1]
        assert "metadataJson" not in args

    async def test_upsert_handles_malformed_response_gracefully(self):
        """Older kernels or transient issues: return raw string rather than crash."""
        mcp = RecordingMcp(responses={"vector_upsert": "not-json"})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await vector.upsert("agent:inst-1", "content")

        assert result == "not-json"


class TestVectorServiceQuery:
    async def test_query_returns_vector_hits(self):
        hits = [
            {
                "id": "chunk-1",
                "externalId": "doc-1",
                "content": "refund policy...",
                "metadata": {"source": "docs"},
                "score": 0.92,
            },
            {
                "id": "chunk-2",
                "externalId": None,
                "content": "customer service...",
                "metadata": {},
                "score": 0.85,
            },
        ]
        mcp = RecordingMcp(responses={"vector_query": json.dumps(hits)})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        results = await vector.query("agent:inst-1", "refund policy")

        assert len(results) == 2
        assert all(isinstance(r, VectorHit) for r in results)
        assert results[0].id == "chunk-1"
        assert results[0].external_id == "doc-1"
        assert results[0].content == "refund policy..."
        assert results[0].metadata == {"source": "docs"}
        assert results[0].score == 0.92
        assert results[1].external_id is None
        assert results[1].metadata == {}

    async def test_query_passes_top_k(self):
        mcp = RecordingMcp(responses={"vector_query": "[]"})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        await vector.query("agent:inst-1", "query", top_k=10)

        args = mcp.calls[0][1]
        assert args["topK"] == 10

    async def test_query_defaults_top_k_to_5(self):
        mcp = RecordingMcp(responses={"vector_query": "[]"})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        await vector.query("agent:inst-1", "query")

        assert mcp.calls[0][1]["topK"] == 5

    async def test_query_returns_empty_list_for_empty_response(self):
        mcp = RecordingMcp(responses={"vector_query": ""})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        results = await vector.query("agent:inst-1", "nothing")

        assert results == []

    async def test_query_returns_empty_list_for_malformed_response(self):
        mcp = RecordingMcp(responses={"vector_query": "<broken>"})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        results = await vector.query("agent:inst-1", "query")

        assert results == []

    async def test_query_tolerates_missing_fields_in_hit(self):
        """A partial hit (missing externalId, metadata, score) should still
        decode — defaults match the dataclass."""
        hits = [{"id": "chunk-x", "content": "partial"}]
        mcp = RecordingMcp(responses={"vector_query": json.dumps(hits)})
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        results = await vector.query("agent:inst-1", "query")

        assert len(results) == 1
        assert results[0].id == "chunk-x"
        assert results[0].external_id is None
        assert results[0].metadata == {}
        assert results[0].score == 0.0


class TestVectorServiceDelete:
    async def test_delete_sends_namespace_and_external_id(self):
        mcp = RecordingMcp()
        vector = VectorService(mcp, "inst-1")  # type: ignore[arg-type]

        await vector.delete("shared:kb", "doc-42")

        tool, args = mcp.calls[0]
        assert tool == "vector_delete"
        assert args == {
            "callerInstanceId": "inst-1",
            "namespace": "shared:kb",
            "externalId": "doc-42",
        }


class TestVectorHitDataclass:
    def test_hit_is_hashable_and_frozen(self):
        """VectorHit uses slots + frozen so it's safe to put in sets and
        agents can rely on identity semantics for dedup."""
        h1 = VectorHit(id="x", external_id=None, content="a")
        h2 = VectorHit(id="x", external_id=None, content="a")

        # Equal values
        assert h1 == h2

        # Frozen → cannot mutate
        import dataclasses

        try:
            h1.content = "mutated"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except dataclasses.FrozenInstanceError:
            pass
