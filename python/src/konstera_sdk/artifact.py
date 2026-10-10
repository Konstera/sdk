"""ArtifactService — content-addressed blob store with provenance trail.

Same content uploaded twice by the same tenant produces the same sha256
(dedup at storage). Each upload still gets its own metadata row so the
audit trail is complete.

Content is transferred as base64 over MCP (JSON-RPC can't carry binary).
For M7b that's fine — expected sizes are tens of KB up to ~25MB. A streaming
API is a later concern once real workloads justify it.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from ._mcp import KernelMcpClient


@dataclass(slots=True, frozen=True)
class PutResult:
    artifact_id: str
    sha256: str
    size_bytes: int
    content_type: str
    storage_uri: str
    dedup: bool
    """True if the content already existed in storage (only metadata row was created)."""


@dataclass(slots=True, frozen=True)
class GetResult:
    content: bytes
    content_type: str
    size_bytes: int
    sha256: str


@dataclass(slots=True, frozen=True)
class HeadResult:
    exists: bool
    sha256: str
    size_bytes: int | None = None
    content_type: str | None = None


@dataclass(slots=True, frozen=True)
class ArtifactListItem:
    artifact_id: str
    sha256: str
    size_bytes: int
    content_type: str
    invocation_id: str | None
    uploaded_at: str
    metadata: dict[str, Any]


class ArtifactService:
    """Kernel artifact-store client. All methods use the agent's own instance ID
    where an uploader is required."""

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def put(
        self,
        content: bytes,
        content_type: str,
        *,
        invocation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PutResult:
        """Upload a blob. Returns the sha256 + storage URI + whether the content
        was already present (dedup=True)."""
        args: dict[str, Any] = {
            "instanceId": self._instance,
            "contentBase64": base64.b64encode(content).decode("ascii"),
            "contentType": content_type,
        }
        if invocation_id is not None:
            args["invocationId"] = invocation_id
        if metadata:
            args["metadataJson"] = json.dumps(metadata, default=str)

        raw = await self._mcp.call_tool_for_result("artifact_put", args)
        d = json.loads(raw) if raw else {}
        return PutResult(
            artifact_id=str(d.get("artifactId", "")),
            sha256=str(d.get("sha256", "")),
            size_bytes=int(d.get("sizeBytes", 0)),
            content_type=str(d.get("contentType", content_type)),
            storage_uri=str(d.get("storageUri", "")),
            dedup=bool(d.get("dedup", False)),
        )

    async def get(self, sha256: str) -> GetResult:
        """Download an artifact by sha256. Raises if not found."""
        raw = await self._mcp.call_tool_for_result(
            "artifact_get",
            {"callerInstanceId": self._instance, "sha256": sha256},
        )
        d = json.loads(raw)
        return GetResult(
            content=base64.b64decode(d["contentBase64"]),
            content_type=str(d.get("contentType", "application/octet-stream")),
            size_bytes=int(d.get("sizeBytes", 0)),
            sha256=str(d.get("sha256", sha256)),
        )

    async def head(self, sha256: str) -> HeadResult:
        """Cheap 'does it exist / how big is it' probe. Never raises for missing."""
        raw = await self._mcp.call_tool_for_result(
            "artifact_head",
            {"callerInstanceId": self._instance, "sha256": sha256},
        )
        d = json.loads(raw)
        return HeadResult(
            exists=bool(d.get("exists", False)),
            sha256=str(d.get("sha256", sha256)),
            size_bytes=int(d["sizeBytes"]) if d.get("sizeBytes") is not None else None,
            content_type=d.get("contentType"),
        )

    async def list_by_uploader(
        self, *, uploader_instance_id: str | None = None, limit: int = 50
    ) -> list[ArtifactListItem]:
        """List artifacts uploaded by an agent instance, most recent first.
        Defaults to this agent's own uploads."""
        raw = await self._mcp.call_tool_for_result(
            "artifact_list_by_uploader",
            {
                "uploaderInstanceId": uploader_instance_id or self._instance,
                "limit": limit,
            },
        )
        items = json.loads(raw) if raw else []
        return [
            ArtifactListItem(
                artifact_id=str(x.get("artifactId", "")),
                sha256=str(x.get("sha256", "")),
                size_bytes=int(x.get("sizeBytes", 0)),
                content_type=str(x.get("contentType", "")),
                invocation_id=x.get("invocationId"),
                uploaded_at=str(x.get("uploadedAt", "")),
                metadata=x.get("metadata") or {},
            )
            for x in items
        ]
