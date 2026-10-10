"""RuleService — versioned, effective-dated policy engine.

Agents READ (via `get`, `get_by_id`, `list`). Humans WRITE via the admin
HTTP endpoints (POST /admin/rules/propose, POST /admin/rules/{id}/decide).
Same maker-checker split as M7c's human/approval flow — including M8's
Segregation of Duties enforcement on the decide endpoint.

Reproducibility contract: when your agent uses a rule to compute
something, record the `rule_id` (not just the `rule_key`) in your output.
Replaying the computation later should call `get_by_id(rule_id)` — that
returns the exact version even if a newer one is now active.

M8: caller instance UUID injected on every read for tenant resolution.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ._mcp import KernelMcpClient


@dataclass(slots=True, frozen=True)
class Rule:
    """A rule row as returned by rule_get / rule_get_by_id.

    Agent code should treat `content` as opaque and pass it into its own
    business logic. The platform doesn't validate content shape — that's
    the agent's job.
    """
    rule_id: str
    rule_key: str
    version: int
    effective_from: str
    description: str | None
    proposed_by: str | None
    proposed_role: str | None
    proposed_at: str
    approved_by: str | None
    approved_role: str | None
    approved_at: str | None
    decision_reason: str | None
    content: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RuleSummary:
    """One row from `list()` without a specific ruleKey — just the current
    active version per key."""
    rule_key: str
    rule_id: str
    version: int
    effective_from: str
    description: str | None


class RuleService:
    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def get(self, rule_key: str, *, at_time: str | None = None) -> Rule:
        """Fetch the active rule for `rule_key`, optionally as of `at_time`
        (ISO-8601). Raises if no active rule matches.

        RECORD the returned rule.rule_id in your agent's output for
        reproducibility — replays should use `get_by_id` with that id."""
        args: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "ruleKey": rule_key,
        }
        if at_time is not None:
            args["atTime"] = at_time
        raw = await self._mcp.call_tool_for_result("rule_get", args)
        return self._parse(raw)

    async def get_by_id(self, rule_id: str) -> Rule:
        """Fetch a specific rule VERSION by its UUID (from a prior get()).
        Version-pinned lookup — always returns the same content regardless
        of whether a newer active version now exists."""
        raw = await self._mcp.call_tool_for_result(
            "rule_get_by_id",
            {"callerInstanceId": self._instance, "ruleId": rule_id},
        )
        return self._parse(raw)

    async def list(
        self, *, rule_key: str | None = None, include_all: bool = False
    ) -> list[Rule] | list[RuleSummary]:
        """If rule_key is provided, returns all active versions of that key
        as `Rule` objects. If include_all=True, includes draft/rejected too.
        If rule_key is omitted, returns one `RuleSummary` per distinct key
        (the current active version), for building an admin/portal overview."""
        args: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "includeAll": include_all,
        }
        if rule_key is not None:
            args["ruleKey"] = rule_key
        raw = await self._mcp.call_tool_for_result("rule_list", args)
        items = json.loads(raw) if raw else []
        if rule_key is not None:
            return [self._parse_dict(x) for x in items]
        return [
            RuleSummary(
                rule_key=str(x.get("ruleKey", "")),
                rule_id=str(x.get("ruleId", "")),
                version=int(x.get("version", 0)),
                effective_from=str(x.get("effectiveFrom", "")),
                description=x.get("description"),
            )
            for x in items
        ]

    @classmethod
    def _parse(cls, raw: str | None) -> Rule:
        d = json.loads(raw) if raw else {}
        return cls._parse_dict(d)

    @staticmethod
    def _parse_dict(d: dict[str, Any]) -> Rule:
        return Rule(
            rule_id=str(d.get("ruleId", "")),
            rule_key=str(d.get("ruleKey", "")),
            version=int(d.get("version", 0)),
            effective_from=str(d.get("effectiveFrom", "")),
            description=d.get("description"),
            proposed_by=d.get("proposedBy"),
            proposed_role=d.get("proposedRole"),
            proposed_at=str(d.get("proposedAt", "")),
            approved_by=d.get("approvedBy"),
            approved_role=d.get("approvedRole"),
            approved_at=d.get("approvedAt"),
            decision_reason=d.get("decisionReason"),
            content=d.get("content") or {},
        )
