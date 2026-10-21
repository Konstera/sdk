"""RuleService — versioned, effective-dated policy registry.

Covers:
- `get(rule_key)` with optional `at_time`
- `get_by_id(rule_id)` for version-pinned reproducible lookups
- `list()` in both modes (keyed → Rule[], no key → RuleSummary[])
- `_parse` / `_parse_dict` static mappers
"""
from __future__ import annotations

import json
from typing import Any

from konstera_sdk.rule import Rule, RuleService, RuleSummary


class RecordingMcp:
    def __init__(self, response: str = ""):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.response = response

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self.response


def _rule_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "ruleId": "rule-abc",
        "ruleKey": "prepayment-classification",
        "version": 2,
        "effectiveFrom": "2026-01-01T00:00:00Z",
        "description": "Classify prepayment vs regular revenue",
        "proposedBy": "user-42",
        "proposedRole": "controller",
        "proposedAt": "2025-12-20T12:00:00Z",
        "approvedBy": "user-7",
        "approvedRole": "cfo",
        "approvedAt": "2025-12-28T09:00:00Z",
        "decisionReason": "Signed off per policy review",
        "content": {"threshold_usd": 5000, "min_service_months": 3},
    }
    base.update(overrides)
    return base


class TestGet:
    async def test_fetches_active_rule_for_key(self):
        mcp = RecordingMcp(response=json.dumps(_rule_dict()))
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        rule = await svc.get("prepayment-classification")

        assert isinstance(rule, Rule)
        assert rule.rule_id == "rule-abc"
        assert rule.version == 2
        assert rule.content["threshold_usd"] == 5000

    async def test_sends_caller_instance_id_and_rule_key(self):
        mcp = RecordingMcp(response=json.dumps(_rule_dict()))
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.get("prepayment-classification")

        tool, args = mcp.calls[0]
        assert tool == "rule_get"
        assert args["callerInstanceId"] == "inst-1"
        assert args["ruleKey"] == "prepayment-classification"
        # at_time omitted when None
        assert "atTime" not in args

    async def test_sends_at_time_when_provided(self):
        mcp = RecordingMcp(response=json.dumps(_rule_dict()))
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.get("prepayment-classification", at_time="2025-06-15T00:00:00Z")

        assert mcp.calls[0][1]["atTime"] == "2025-06-15T00:00:00Z"

    async def test_empty_response_still_returns_rule_with_defaults(self):
        """Edge case: kernel returns "" — SDK produces a Rule with empty fields
        rather than raising. Callers should check rule_id truthiness if they
        want to be defensive about this."""
        mcp = RecordingMcp(response="")
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]
        rule = await svc.get("nonexistent")
        assert rule.rule_id == ""
        assert rule.content == {}


class TestGetById:
    async def test_fetches_version_pinned_rule(self):
        mcp = RecordingMcp(response=json.dumps(_rule_dict(version=1)))
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        rule = await svc.get_by_id("rule-abc")

        assert rule.rule_id == "rule-abc"
        assert rule.version == 1

    async def test_sends_caller_and_rule_id(self):
        mcp = RecordingMcp(response=json.dumps(_rule_dict()))
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.get_by_id("rule-xyz")

        tool, args = mcp.calls[0]
        assert tool == "rule_get_by_id"
        assert args == {"callerInstanceId": "inst-1", "ruleId": "rule-xyz"}


class TestListWithKey:
    async def test_returns_rule_objects_when_key_given(self):
        rules = [_rule_dict(ruleId=f"rule-{i}", version=i + 1) for i in range(3)]
        mcp = RecordingMcp(response=json.dumps(rules))
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.list(rule_key="prepayment-classification")

        assert len(result) == 3
        assert all(isinstance(r, Rule) for r in result)
        assert [r.version for r in result] == [1, 2, 3]

    async def test_sends_rule_key_and_include_all_defaults_false(self):
        mcp = RecordingMcp(response="[]")
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.list(rule_key="k")

        args = mcp.calls[0][1]
        assert args["ruleKey"] == "k"
        assert args["includeAll"] is False

    async def test_include_all_true_passes_through(self):
        mcp = RecordingMcp(response="[]")
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.list(rule_key="k", include_all=True)

        assert mcp.calls[0][1]["includeAll"] is True


class TestListWithoutKey:
    async def test_returns_summaries_when_no_key_given(self):
        """Without a specific key, kernel returns one summary per distinct
        key (the current active version) — for portal/admin UIs."""
        summaries = [
            {
                "ruleKey": "prepayment-classification",
                "ruleId": "rule-abc",
                "version": 2,
                "effectiveFrom": "2026-01-01T00:00:00Z",
                "description": "Classify prepayment",
            },
            {
                "ruleKey": "credit-limit-tier",
                "ruleId": "rule-xyz",
                "version": 1,
                "effectiveFrom": "2025-06-01T00:00:00Z",
                "description": None,
            },
        ]
        mcp = RecordingMcp(response=json.dumps(summaries))
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.list()

        assert len(result) == 2
        assert all(isinstance(r, RuleSummary) for r in result)
        assert result[0].rule_key == "prepayment-classification"
        assert result[0].version == 2
        assert result[1].description is None

    async def test_rule_key_omitted_when_none(self):
        mcp = RecordingMcp(response="[]")
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]
        await svc.list()
        assert "ruleKey" not in mcp.calls[0][1]

    async def test_empty_response_returns_empty_list(self):
        mcp = RecordingMcp(response="")
        svc = RuleService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await svc.list() == []


class TestParseDict:
    def test_full_payload_populates_all_fields(self):
        rule = RuleService._parse_dict(_rule_dict())
        assert rule.rule_id == "rule-abc"
        assert rule.rule_key == "prepayment-classification"
        assert rule.version == 2
        assert rule.proposed_by == "user-42"
        assert rule.approved_by == "user-7"
        assert rule.content == {"threshold_usd": 5000, "min_service_months": 3}

    def test_tolerates_missing_optional_fields(self):
        rule = RuleService._parse_dict(
            {"ruleId": "x", "ruleKey": "y", "version": 1, "effectiveFrom": "t"}
        )
        assert rule.description is None
        assert rule.proposed_by is None
        assert rule.approved_by is None
        assert rule.content == {}

    def test_null_content_defaults_to_empty_dict(self):
        rule = RuleService._parse_dict({"ruleId": "x", "content": None})
        assert rule.content == {}
