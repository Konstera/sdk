"""HumanService — human-in-the-loop approvals with tier-based routing + SoD.

Covers:
- `HumanDecision.is_resolved` / `is_approved` properties
- `request()` with all optional args (detail, options, submitter_role,
  invocation_id, parent_approval_id, wait_seconds for T1 polling)
- `get()` + `wait()` + `list_pending()` surface
- `_from_dict` mapper for every field including Literal types
"""
from __future__ import annotations

import json
from typing import Any

from konstera_sdk.human import HumanDecision, HumanService


class RecordingMcp:
    def __init__(self, responses: list[str] | None = None):
        """A list of responses that are returned in order per call. Useful
        when the service makes multiple calls (e.g. request → wait)."""
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses = responses or []
        self._next = 0

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        if self._next < len(self.responses):
            r = self.responses[self._next]
            self._next += 1
            return r
        return ""


def _decision_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "approvalId": "appr-1",
        "kind": "post-journal",
        "tier": "T1",
        "status": "pending",
        "summary": "Post batch B1234",
        "submitterInstanceId": "inst-1",
        "submitterRole": "agent",
        "invocationId": "inv-9",
        "options": ["approve", "reject"],
        "decision": None,
        "approverActorId": None,
        "approverRole": None,
        "decisionReason": None,
        "submittedAt": "2026-10-21T12:00:00Z",
        "decidedAt": None,
        "expiresAt": None,
        "detail": {"batch_id": "B1234"},
    }
    base.update(overrides)
    return base


class TestDecisionProperties:
    def test_pending_is_not_resolved(self):
        d = HumanService._from_dict(_decision_dict(status="pending"))
        assert d.is_resolved is False
        assert d.is_approved is False

    def test_approved_is_resolved_and_approved(self):
        d = HumanService._from_dict(_decision_dict(status="approved"))
        assert d.is_resolved is True
        assert d.is_approved is True

    def test_rejected_is_resolved_not_approved(self):
        d = HumanService._from_dict(_decision_dict(status="rejected"))
        assert d.is_resolved is True
        assert d.is_approved is False

    def test_blocked_is_resolved_not_approved(self):
        """T0 tier → kernel blocks before human sees it; status=blocked
        is a terminal, non-approved state."""
        d = HumanService._from_dict(_decision_dict(status="blocked"))
        assert d.is_resolved is True
        assert d.is_approved is False

    def test_expired_is_resolved_not_approved(self):
        d = HumanService._from_dict(_decision_dict(status="expired"))
        assert d.is_resolved is True
        assert d.is_approved is False


class TestRequestMinimal:
    async def test_minimal_t1_sends_instance_kind_tier_summary(self):
        mcp = RecordingMcp(responses=[json.dumps(_decision_dict())])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.request(kind="k", tier="T1", summary="s")

        assert isinstance(result, HumanDecision)
        tool, args = mcp.calls[0]
        assert tool == "human_submit"
        assert args == {
            "instanceId": "inst-1",
            "kind": "k",
            "tier": "T1",
            "summary": "s",
        }

    async def test_optional_fields_included_when_provided(self):
        mcp = RecordingMcp(responses=[json.dumps(_decision_dict())])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.request(
            kind="k",
            tier="T1",
            summary="s",
            detail={"foo": "bar"},
            options=["approve", "reject", "rework"],
            submitter_role="controller",
            invocation_id="inv-9",
            parent_approval_id="appr-prev",
        )

        args = mcp.calls[0][1]
        assert json.loads(args["detailJson"]) == {"foo": "bar"}
        assert json.loads(args["optionsJson"]) == ["approve", "reject", "rework"]
        assert args["submitterRole"] == "controller"
        assert args["invocationId"] == "inv-9"
        assert args["parentApprovalId"] == "appr-prev"


class TestRequestWithWait:
    """wait_seconds triggers a client-side poll when T1 returns pending."""

    async def test_wait_fires_second_call_when_pending(self):
        mcp = RecordingMcp(
            responses=[
                json.dumps(_decision_dict(status="pending")),
                json.dumps(_decision_dict(status="approved", decision="approve")),
            ]
        )
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.request(kind="k", tier="T1", summary="s", wait_seconds=30)

        # Two calls: submit → wait
        assert [c[0] for c in mcp.calls] == ["human_submit", "human_wait"]
        # Final decision reflects the post-wait state
        assert result.status == "approved"
        assert result.is_approved
        # Wait call includes the approval_id + timeout
        wait_args = mcp.calls[1][1]
        assert wait_args["approvalId"] == "appr-1"
        assert wait_args["timeoutSeconds"] == 30

    async def test_wait_skipped_when_already_resolved(self):
        """T3 and friends come back already-decided — don't double up on polls."""
        mcp = RecordingMcp(
            responses=[json.dumps(_decision_dict(status="approved", decision="approve"))]
        )
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.request(kind="k", tier="T3", summary="s", wait_seconds=30)

        # Only one call — submit, no wait
        assert len(mcp.calls) == 1
        assert mcp.calls[0][0] == "human_submit"
        assert result.is_approved

    async def test_no_wait_when_wait_seconds_falsy(self):
        """wait_seconds=0 / None → never poll."""
        mcp = RecordingMcp(responses=[json.dumps(_decision_dict(status="pending"))])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await svc.request(kind="k", tier="T1", summary="s")

        assert len(mcp.calls) == 1
        assert result.status == "pending"


class TestGet:
    async def test_fetches_by_approval_id(self):
        mcp = RecordingMcp(responses=[json.dumps(_decision_dict())])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        decision = await svc.get("appr-1")

        assert isinstance(decision, HumanDecision)
        assert decision.approval_id == "appr-1"
        tool, args = mcp.calls[0]
        assert tool == "human_get"
        assert args == {"callerInstanceId": "inst-1", "approvalId": "appr-1"}


class TestWait:
    async def test_fetches_with_default_timeout(self):
        mcp = RecordingMcp(responses=[json.dumps(_decision_dict())])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.wait("appr-1")

        args = mcp.calls[0][1]
        assert args["timeoutSeconds"] == 30

    async def test_custom_timeout(self):
        mcp = RecordingMcp(responses=[json.dumps(_decision_dict())])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.wait("appr-1", timeout_seconds=60)

        args = mcp.calls[0][1]
        assert args["timeoutSeconds"] == 60


class TestListPending:
    async def test_lists_tenant_pending_by_default(self):
        decisions = [_decision_dict(approvalId=f"appr-{i}") for i in range(3)]
        mcp = RecordingMcp(responses=[json.dumps(decisions)])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        results = await svc.list_pending()

        assert len(results) == 3
        assert all(isinstance(r, HumanDecision) for r in results)
        args = mcp.calls[0][1]
        assert args["callerInstanceId"] == "inst-1"
        assert args["limit"] == 50
        # mine_only=False → no submitter filter
        assert "submitterInstanceId" not in args

    async def test_mine_only_filters_to_self(self):
        mcp = RecordingMcp(responses=["[]"])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.list_pending(mine_only=True)

        args = mcp.calls[0][1]
        assert args["submitterInstanceId"] == "inst-1"

    async def test_custom_limit(self):
        mcp = RecordingMcp(responses=["[]"])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]

        await svc.list_pending(limit=10)

        assert mcp.calls[0][1]["limit"] == 10

    async def test_empty_response_returns_empty_list(self):
        mcp = RecordingMcp(responses=[""])
        svc = HumanService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await svc.list_pending() == []


class TestFromDictMapper:
    def test_populates_all_fields(self):
        d = HumanService._from_dict(_decision_dict())

        assert d.approval_id == "appr-1"
        assert d.kind == "post-journal"
        assert d.tier == "T1"
        assert d.status == "pending"
        assert d.summary == "Post batch B1234"
        assert d.submitter_instance_id == "inst-1"
        assert d.submitter_role == "agent"
        assert d.invocation_id == "inv-9"
        assert d.options == ["approve", "reject"]
        assert d.detail == {"batch_id": "B1234"}

    def test_tolerates_missing_optional_fields(self):
        """A minimal response (just approval_id) should still produce a
        well-defined HumanDecision — missing fields take sensible defaults."""
        d = HumanService._from_dict({"approvalId": "appr-x"})

        assert d.approval_id == "appr-x"
        assert d.kind == ""
        assert d.tier == "T1"  # default
        assert d.status == "pending"  # default
        assert d.summary == ""
        assert d.options == []
        assert d.detail == {}
        assert d.invocation_id is None
        assert d.decided_at is None

    def test_null_detail_defaults_to_empty_dict(self):
        d = HumanService._from_dict(_decision_dict(detail=None))
        assert d.detail == {}

    def test_approved_decision_populates_decision_fields(self):
        d = HumanService._from_dict(
            _decision_dict(
                status="approved",
                decision="approve",
                approverActorId="user-42",
                approverRole="cfo",
                decisionReason="Signed off",
                decidedAt="2026-10-21T13:00:00Z",
            )
        )
        assert d.decision == "approve"
        assert d.approver_actor_id == "user-42"
        assert d.approver_role == "cfo"
        assert d.decision_reason == "Signed off"
        assert d.decided_at == "2026-10-21T13:00:00Z"
