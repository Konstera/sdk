"""CostService — record non-LLM cost events.

Thin service — one method with many optional fields. Tests verify every
optional field is only sent when provided (so the kernel doesn't see
nulls where it expects omission).
"""
from __future__ import annotations

import json
from typing import Any

from konstera_sdk.cost import CostService


class RecordingMcp:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return ""


class TestRecord:
    async def test_minimal_args_sends_instance_kind_cost(self):
        mcp = RecordingMcp()
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]

        await cost.record(kind="tool", cost_usd=0.01)

        tool, args = mcp.calls[0]
        assert tool == "cost_record"
        assert args == {"instanceId": "inst-1", "kind": "tool", "costUsd": 0.01}

    async def test_optional_fields_omitted_when_none(self):
        mcp = RecordingMcp()
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]

        await cost.record(kind="other", cost_usd=0.0)

        args = mcp.calls[0][1]
        assert "modelId" not in args
        assert "inputTokens" not in args
        assert "outputTokens" not in args
        assert "cachedInputTokens" not in args
        assert "metadataJson" not in args
        assert "invocationId" not in args

    async def test_all_optional_fields_included_when_provided(self):
        mcp = RecordingMcp()
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]

        await cost.record(
            kind="llm",
            cost_usd=0.0023,
            model="claude-sonnet-4-6",
            invocation_id="inv-9",
            input_tokens=100,
            output_tokens=50,
            cached_input_tokens=20,
            metadata={"caller": "narrator"},
        )

        args = mcp.calls[0][1]
        assert args["instanceId"] == "inst-1"
        assert args["kind"] == "llm"
        assert args["costUsd"] == 0.0023
        assert args["modelId"] == "claude-sonnet-4-6"
        assert args["invocationId"] == "inv-9"
        assert args["inputTokens"] == 100
        assert args["outputTokens"] == 50
        assert args["cachedInputTokens"] == 20
        assert json.loads(args["metadataJson"]) == {"caller": "narrator"}

    async def test_zero_cost_allowed(self):
        """Spec: cost_usd must be >= 0. Zero is fine (e.g. cached response)."""
        mcp = RecordingMcp()
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]
        await cost.record(kind="llm", cost_usd=0.0)
        assert mcp.calls[0][1]["costUsd"] == 0.0

    async def test_metadata_empty_dict_treated_as_no_metadata(self):
        """Empty dict shouldn't send metadataJson='{}' — truthy check skips."""
        mcp = RecordingMcp()
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]
        await cost.record(kind="tool", cost_usd=0.01, metadata={})
        assert "metadataJson" not in mcp.calls[0][1]

    async def test_metadata_serialises_non_json_values(self):
        import datetime as dt

        mcp = RecordingMcp()
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]
        await cost.record(
            kind="tool", cost_usd=0.01, metadata={"recorded_at": dt.datetime(2026, 1, 1)}
        )
        metadata_json = mcp.calls[0][1]["metadataJson"]
        assert "2026-01-01" in metadata_json

    async def test_zero_token_counts_still_sent(self):
        """A zero-token result is semantically different from an omitted
        token count. If the agent passes input_tokens=0, we send it."""
        mcp = RecordingMcp()
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]
        await cost.record(kind="llm", cost_usd=0.0, input_tokens=0, output_tokens=0)
        args = mcp.calls[0][1]
        assert args["inputTokens"] == 0
        assert args["outputTokens"] == 0
