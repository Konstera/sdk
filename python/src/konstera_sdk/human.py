"""HumanService — human-in-the-loop approvals with tier-based routing + SoD.

Tier semantics (from the finance requirements doc, Table 18):
  T0 Blocked       → kernel refuses at submission; agent gets status=blocked
  T1 Prepare-only  → sits pending until a human acts
  T2 Auto-stage    → auto-approved by kernel; audit trail preserved for
                     retrospective review
  T3 Straight-through → auto-approved by kernel (mature whitelisted rule)

Typical agent flow:
    result = await ctx.human.request(
        kind="post-bc-journal", tier="T1",
        summary="Post journal batch B1234 to BC company XYZ",
        detail={"batch_id": "B1234", "total": 45000.00},
        wait_seconds=30,          # optional; polls up to this long
    )
    if result.decision == "approve":
        # proceed
    elif result.status == "pending":
        # store approval_id, come back to it in a later invocation

The `wait_seconds` argument is client-side polling. Long waits (hours)
belong to Temporal signals (M11) — for now, submit + return `pending`
and check back in a later invocation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from ._mcp import KernelMcpClient

Tier = Literal["T0", "T1", "T2", "T3"]
Status = Literal["pending", "approved", "rejected", "reworked", "blocked", "expired"]
Decision = Literal["approve", "reject", "rework"]


@dataclass(slots=True, frozen=True)
class HumanDecision:
    """Snapshot of an approval — same shape whether just-submitted or fetched later."""
    approval_id: str
    kind: str
    tier: Tier
    status: Status
    summary: str
    submitter_instance_id: str
    submitter_role: str | None
    invocation_id: str | None
    options: list[str]
    decision: Decision | None
    approver_actor_id: str | None
    approver_role: str | None
    decision_reason: str | None
    submitted_at: str
    decided_at: str | None
    expires_at: str | None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_resolved(self) -> bool:
        """True if the approval has left the pending state."""
        return self.status != "pending"

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"


class HumanService:
    """Kernel human-approval client. Uses the agent's own instance ID as
    the submitter for every request."""

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def request(
        self,
        *,
        kind: str,
        tier: Tier,
        summary: str,
        detail: dict[str, Any] | None = None,
        options: list[str] | None = None,
        submitter_role: str | None = None,
        invocation_id: str | None = None,
        wait_seconds: int | None = None,
        parent_approval_id: str | None = None,
    ) -> HumanDecision:
        """Submit an approval request.

        If `tier` is T0/T2/T3 kernel resolves synchronously — result comes
        back already decided. If T1, result is pending; pass `wait_seconds`
        (1-60) to poll for a decision before returning, or accept the
        pending state and check back later with `get(approval_id)`.

        `parent_approval_id` links a redraft to the approval it replaces, so
        the kernel can treat both as one draft chain (ADR-027). Omitted from
        the call when None.
        """
        args: dict[str, Any] = {
            "instanceId": self._instance,
            "kind": kind,
            "tier": tier,
            "summary": summary,
        }
        if detail is not None:
            args["detailJson"] = json.dumps(detail, default=str)
        if options is not None:
            args["optionsJson"] = json.dumps(options)
        if submitter_role is not None:
            args["submitterRole"] = submitter_role
        if invocation_id is not None:
            args["invocationId"] = invocation_id
        if parent_approval_id is not None:
            args["parentApprovalId"] = parent_approval_id

        raw = await self._mcp.call_tool_for_result("human_submit", args)
        decision = self._parse(raw)

        # Client-side wait — only useful for T1. T0/T2/T3 already resolved.
        if wait_seconds and decision.status == "pending":
            decision = await self.wait(decision.approval_id, timeout_seconds=wait_seconds)
        return decision

    async def get(self, approval_id: str) -> HumanDecision:
        """Fetch the current state of an approval."""
        raw = await self._mcp.call_tool_for_result(
            "human_get",
            {"callerInstanceId": self._instance, "approvalId": approval_id},
        )
        return self._parse(raw)

    async def wait(self, approval_id: str, *, timeout_seconds: int = 30) -> HumanDecision:
        """Poll for up to `timeout_seconds` (1-60). Returns as soon as the
        approval leaves pending, or the still-pending state at timeout."""
        raw = await self._mcp.call_tool_for_result(
            "human_wait",
            {
                "callerInstanceId": self._instance,
                "approvalId": approval_id,
                "timeoutSeconds": timeout_seconds,
            },
        )
        return self._parse(raw)

    async def list_pending(
        self, *, mine_only: bool = False, limit: int = 50
    ) -> list[HumanDecision]:
        """List pending approvals in the tenant. If `mine_only`, filter to
        approvals this agent instance submitted."""
        args: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "limit": limit,
        }
        if mine_only:
            args["submitterInstanceId"] = self._instance
        raw = await self._mcp.call_tool_for_result("human_list_pending", args)
        items = json.loads(raw) if raw else []
        return [self._from_dict(x) for x in items]

    @classmethod
    def _parse(cls, raw: str | None) -> HumanDecision:
        d = json.loads(raw) if raw else {}
        return cls._from_dict(d)

    @staticmethod
    def _from_dict(d: dict[str, Any]) -> HumanDecision:
        return HumanDecision(
            approval_id=str(d.get("approvalId", "")),
            kind=str(d.get("kind", "")),
            tier=str(d.get("tier", "T1")),  # type: ignore[arg-type]
            status=str(d.get("status", "pending")),  # type: ignore[arg-type]
            summary=str(d.get("summary", "")),
            submitter_instance_id=str(d.get("submitterInstanceId", "")),
            submitter_role=d.get("submitterRole"),
            invocation_id=d.get("invocationId"),
            options=list(d.get("options") or []),
            decision=d.get("decision"),
            approver_actor_id=d.get("approverActorId"),
            approver_role=d.get("approverRole"),
            decision_reason=d.get("decisionReason"),
            submitted_at=str(d.get("submittedAt", "")),
            decided_at=d.get("decidedAt"),
            expires_at=d.get("expiresAt"),
            detail=d.get("detail") or {},
        )
