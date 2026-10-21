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
        """Fetch the active rule for a given key.

        Args:
            rule_key: Business-level key (e.g. `"prepayment-classification"`,
                `"credit-limit-tier"`). Multiple versions may exist; this
                returns the active one as of `at_time`.
            at_time: Optional ISO-8601 timestamp. If provided, returns the
                version that was active at that moment (for retrospective
                audits or reprocessing historical data). Omit to get "now".

        Returns:
            `Rule` dataclass with the full version metadata + `content` dict.

        Raises:
            RuntimeError: If no active rule matches the key at the requested
                time (platform surfaces this as a specific kernel error).

        **Reproducibility**: record the returned `rule.rule_id` in your agent's
        output. Replays should use `get_by_id(rule_id)` so the computation
        uses the exact same version even if a newer one is now active.

        Example:
            >>> rule = await ctx.rule.get("prepayment-classification")
            >>> if order.total > rule.content["threshold_usd"]:
            ...     await ctx.human.request(kind="prepayment-review", tier="T1", ...)
            >>> # Save rule.rule_id in the audit trail for later replay
        """
        args: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "ruleKey": rule_key,
        }
        if at_time is not None:
            args["atTime"] = at_time
        raw = await self._mcp.call_tool_for_result("rule_get", args)
        return self._parse(raw)

    async def get_by_id(self, rule_id: str) -> Rule:
        """Fetch a specific rule VERSION by its UUID.

        Args:
            rule_id: The UUID from a prior `get()` call's `rule.rule_id`.

        Returns:
            `Rule` with the exact pinned version. Reproducible: always
            returns the same content regardless of whether a newer active
            version now exists.

        Example:
            >>> # Replay an old computation using the rule that was active then
            >>> original_rule_id = audit_trail["rule_id"]
            >>> rule = await ctx.rule.get_by_id(original_rule_id)
            >>> # recompute with historical rule
        """
        raw = await self._mcp.call_tool_for_result(
            "rule_get_by_id",
            {"callerInstanceId": self._instance, "ruleId": rule_id},
        )
        return self._parse(raw)

    async def list(
        self, *, rule_key: str | None = None, include_all: bool = False
    ) -> list[Rule] | list[RuleSummary]:
        """List rules in two modes based on arguments.

        Args:
            rule_key: If provided, lists all versions of that single key.
                Returns `list[Rule]` with full content.
            include_all: Only meaningful with `rule_key`. If `True`, includes
                draft/rejected versions. If `False` (default), active only.

        Returns:
            Depends on arguments:
            - With `rule_key`: `list[Rule]` — full version history for that key.
            - Without `rule_key`: `list[RuleSummary]` — one entry per distinct
              key (the current active version). Useful for building an
              admin overview.

        Example:
            >>> # Full version history of a specific rule
            >>> versions = await ctx.rule.list(rule_key="prepayment-classification")
            >>> for v in versions:
            ...     print(f"v{v.version} effective {v.effective_from}")
            >>>
            >>> # Portal overview — one row per rule
            >>> summaries = await ctx.rule.list()
            >>> for s in summaries:
            ...     print(f"{s.rule_key} v{s.version}")
        """
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
