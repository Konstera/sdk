"""CostService — record non-LLM cost events + read rolling spend summaries.

Record: one method with many optional fields. Tests verify every optional
field is only sent when provided (so the kernel doesn't see nulls where
it expects omission).

Summary: fetch a rolling cost window for this instance. Tests verify arg
packing, feature-off / empty-response handling, and the from_dict parse.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from konstera_sdk.cost import CostService, CostSummary


class RecordingMcp:
    def __init__(self, responses: dict[str, str] | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._responses = responses or {}

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self._responses.get(tool, "")


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


class TestSummary:
    async def test_default_window_hours_is_24(self):
        payload = {
            "window_hours": 24,
            "since": "2026-01-01T00:00:00Z",
            "until": "2026-01-02T00:00:00Z",
            "total_usd": 1.23,
            "by_kind": {"llm": 1.0, "tool": 0.23},
        }
        mcp = RecordingMcp(responses={"cost_summary": json.dumps(payload)})
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]

        summary = await cost.summary()

        assert summary is not None
        assert summary.window_hours == 24
        assert summary.total_usd == 1.23
        assert summary.by_kind == {"llm": 1.0, "tool": 0.23}
        tool, args = mcp.calls[0]
        assert tool == "cost_summary"
        assert args == {"instanceId": "inst-1", "windowHours": 24}

    async def test_custom_window_hours_sent(self):
        mcp = RecordingMcp(
            responses={
                "cost_summary": json.dumps(
                    {"window_hours": 1, "since": "x", "until": "y", "total_usd": 0.0, "by_kind": {}}
                )
            }
        )
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]
        await cost.summary(window_hours=1)
        assert mcp.calls[0][1]["windowHours"] == 1

    async def test_window_hours_below_one_raises(self):
        cost = CostService(RecordingMcp(), "inst-1")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="window_hours must be >= 1"):
            await cost.summary(window_hours=0)

    async def test_empty_response_returns_none(self):
        mcp = RecordingMcp(responses={"cost_summary": ""})
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cost.summary() is None

    async def test_null_response_returns_none(self):
        mcp = RecordingMcp(responses={"cost_summary": "null"})
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cost.summary() is None

    async def test_non_dict_response_returns_none(self):
        """Defensive: if the kernel ever returns a scalar / array (e.g. a
        feature-disabled list), fall through to None rather than crash."""
        mcp = RecordingMcp(responses={"cost_summary": "[]"})
        cost = CostService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cost.summary() is None

    async def test_from_dict_tolerates_missing_fields(self):
        """CostSummary.from_dict shouldn't crash on partial payloads during
        schema evolution — defaults kick in for every field."""
        s = CostSummary.from_dict({})
        assert s.window_hours == 0
        assert s.total_usd == 0.0
        assert s.by_kind == {}
