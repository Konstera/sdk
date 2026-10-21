"""ArtifactService — content-addressed blob store with provenance.

Covers:
- put() — base64 encoding, dedup flag, metadata serialisation
- get() — base64 decoding, sha256 verification pass-through
- head() — cheap existence probe, size optional
- list_by_uploader() — filtering by uploader_instance_id, limit
"""
from __future__ import annotations

import base64
import json
from typing import Any

from konstera_sdk.artifact import (
    ArtifactListItem,
    ArtifactService,
    GetResult,
    HeadResult,
    PutResult,
)


class RecordingMcp:
    def __init__(self, response: str = ""):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.response = response

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self.response


class TestPut:
    async def test_encodes_content_to_base64(self):
        mcp = RecordingMcp(
            response=json.dumps(
                {
                    "artifactId": "art-1",
                    "sha256": "abc123",
                    "sizeBytes": 5,
                    "contentType": "text/plain",
                    "storageUri": "minio://bucket/abc123",
                    "dedup": False,
                }
            )
        )
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.put(b"hello", content_type="text/plain")

        tool, args = mcp.calls[0]
        assert tool == "artifact_put"
        assert args["instanceId"] == "inst-1"
        assert args["contentType"] == "text/plain"
        # Base64 of b"hello" is "aGVsbG8="
        assert args["contentBase64"] == "aGVsbG8="
        assert isinstance(result, PutResult)
        assert result.artifact_id == "art-1"
        assert result.sha256 == "abc123"
        assert result.dedup is False

    async def test_dedup_true_when_content_already_existed(self):
        mcp = RecordingMcp(
            response=json.dumps(
                {
                    "artifactId": "art-2",
                    "sha256": "same-hash",
                    "sizeBytes": 5,
                    "contentType": "text/plain",
                    "storageUri": "minio://bucket/same-hash",
                    "dedup": True,
                }
            )
        )
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.put(b"hello", content_type="text/plain")

        assert result.dedup is True

    async def test_optional_invocation_id_included(self):
        mcp = RecordingMcp(response="{}")
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.put(b"x", content_type="text/plain", invocation_id="inv-5")

        assert mcp.calls[0][1]["invocationId"] == "inv-5"

    async def test_optional_invocation_id_omitted_when_none(self):
        mcp = RecordingMcp(response="{}")
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.put(b"x", content_type="text/plain")

        assert "invocationId" not in mcp.calls[0][1]

    async def test_metadata_serialised_to_json(self):
        mcp = RecordingMcp(response="{}")
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.put(
            b"x",
            content_type="application/pdf",
            metadata={"doc_type": "invoice", "source_id": 42},
        )

        md = mcp.calls[0][1]["metadataJson"]
        assert json.loads(md) == {"doc_type": "invoice", "source_id": 42}

    async def test_empty_metadata_omitted(self):
        mcp = RecordingMcp(response="{}")
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.put(b"x", content_type="text/plain", metadata={})

        assert "metadataJson" not in mcp.calls[0][1]

    async def test_binary_content_round_trips_through_base64(self):
        mcp = RecordingMcp(response="{}")
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        content = bytes(range(256))  # Full byte range — tricky for text decoders

        await svc.put(content, content_type="application/octet-stream")

        encoded = mcp.calls[0][1]["contentBase64"]
        assert base64.b64decode(encoded) == content

    async def test_falls_back_to_input_content_type_when_response_missing(self):
        """If kernel returns a PutResult without contentType, SDK echoes
        what the caller sent — nicer than ""."""
        mcp = RecordingMcp(
            response=json.dumps(
                {
                    "artifactId": "a",
                    "sha256": "s",
                    "sizeBytes": 1,
                    "storageUri": "u",
                    "dedup": False,
                }
            )
        )
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.put(b"x", content_type="image/png")

        assert result.content_type == "image/png"


class TestGet:
    async def test_decodes_base64_content(self):
        content = b"the quick brown fox"
        payload = {
            "contentBase64": base64.b64encode(content).decode("ascii"),
            "contentType": "text/plain",
            "sizeBytes": len(content),
            "sha256": "fakehash",
        }
        mcp = RecordingMcp(response=json.dumps(payload))
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.get("fakehash")

        assert isinstance(result, GetResult)
        assert result.content == content
        assert result.size_bytes == 19
        assert result.content_type == "text/plain"

    async def test_round_trips_binary_content(self):
        content = bytes(range(256))
        payload = {
            "contentBase64": base64.b64encode(content).decode("ascii"),
            "contentType": "application/octet-stream",
            "sizeBytes": 256,
            "sha256": "h",
        }
        mcp = RecordingMcp(response=json.dumps(payload))
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.get("h")

        assert result.content == content

    async def test_sends_caller_and_sha256(self):
        payload = {
            "contentBase64": base64.b64encode(b"").decode("ascii"),
            "contentType": "x",
            "sizeBytes": 0,
            "sha256": "s",
        }
        mcp = RecordingMcp(response=json.dumps(payload))
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.get("s")

        tool, args = mcp.calls[0]
        assert tool == "artifact_get"
        assert args == {"callerInstanceId": "inst-1", "sha256": "s"}

    async def test_defaults_content_type_when_response_missing_it(self):
        payload = {
            "contentBase64": base64.b64encode(b"x").decode("ascii"),
            "sizeBytes": 1,
            "sha256": "s",
        }
        mcp = RecordingMcp(response=json.dumps(payload))
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.get("s")

        assert result.content_type == "application/octet-stream"


class TestHead:
    async def test_exists_true_populates_all_fields(self):
        mcp = RecordingMcp(
            response=json.dumps(
                {
                    "exists": True,
                    "sha256": "h",
                    "sizeBytes": 1024,
                    "contentType": "image/png",
                }
            )
        )
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.head("h")

        assert isinstance(result, HeadResult)
        assert result.exists is True
        assert result.size_bytes == 1024
        assert result.content_type == "image/png"

    async def test_exists_false_with_only_sha256(self):
        """Not-found response — size and content_type stay None rather than 0."""
        mcp = RecordingMcp(
            response=json.dumps({"exists": False, "sha256": "missing-hash"})
        )
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.head("missing-hash")

        assert result.exists is False
        assert result.sha256 == "missing-hash"
        assert result.size_bytes is None
        assert result.content_type is None


class TestListByUploader:
    async def test_defaults_to_self_as_uploader(self):
        mcp = RecordingMcp(response="[]")
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.list_by_uploader()

        args = mcp.calls[0][1]
        assert args["uploaderInstanceId"] == "inst-1"
        assert args["limit"] == 50

    async def test_can_override_uploader_and_limit(self):
        mcp = RecordingMcp(response="[]")
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.list_by_uploader(uploader_instance_id="other-inst", limit=200)

        args = mcp.calls[0][1]
        assert args["uploaderInstanceId"] == "other-inst"
        assert args["limit"] == 200

    async def test_decodes_list_items(self):
        items = [
            {
                "artifactId": "a-1",
                "sha256": "h1",
                "sizeBytes": 100,
                "contentType": "text/plain",
                "invocationId": "inv-1",
                "uploadedAt": "2026-10-21T12:00:00Z",
                "metadata": {"source": "x"},
            },
            {
                "artifactId": "a-2",
                "sha256": "h2",
                "sizeBytes": 200,
                "contentType": "image/png",
                "invocationId": None,
                "uploadedAt": "2026-10-21T13:00:00Z",
                "metadata": {},
            },
        ]
        mcp = RecordingMcp(response=json.dumps(items))
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]

        results = await svc.list_by_uploader()

        assert len(results) == 2
        assert all(isinstance(r, ArtifactListItem) for r in results)
        assert results[0].artifact_id == "a-1"
        assert results[0].invocation_id == "inv-1"
        assert results[1].invocation_id is None

    async def test_empty_response_returns_empty_list(self):
        mcp = RecordingMcp(response="")
        svc = ArtifactService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await svc.list_by_uploader() == []
