"""review-actions-demo — DEMO agent (not for any real tenant).

Puts canned drafts into the Reviewer Inbox so every kind of review action
and every draft outcome can be tried by hand and seen
in Agents › Overview › Quality & value and in Reports.

Run test (manual invoke) with an empty input to get the next canned case, or
a JSON payload to choose:
  {"case": 1..5}                      one of the canned cases below
  {"subject": "...", "message": "...", "customer": "...", "draft": "..."}
  {"fail_send": true}                 approving it returns a failed send
  {"crash": true}                     the run itself fails (Run success)

Decisions come back as invocation_type=on_decision. Escalate / Open case /
Email team are dispatched by the platform (webhook / api / email), not here.
All names and addresses are made up.
"""
from __future__ import annotations

from konstera_sdk import Agent, AgentContext, AgentRequest, AgentResponse, run

CASES = [
    {   # 1: a good draft — try Send (sent as is)
        "subject": "Where is my order DEMO-1001?",
        "customer": "asha.demo@example.test", "name": "Asha (demo)",
        "message": "Hi, I ordered a blue kettle last week (DEMO-1001). Any update on delivery?",
        "draft": "Hi Asha,\n\nYour order DEMO-1001 left our warehouse yesterday and should arrive within 2 working days. "
                 "You'll get a tracking link by email today.\n\nBest regards,\nDemo Support",
    },
    {   # 2: a draft with a mistake — try Edit (sent with an edit)
        "subject": "Refund for a damaged mug",
        "customer": "ben.demo@example.test", "name": "Ben (demo)",
        "message": "The mug in order DEMO-2002 arrived broken. Can I get a refund?",
        "draft": "Hi Ben,\n\nSorry about that. We have issued a refund of £500 to your card.\n\nBest regards,\nDemo Support",
    },
    {   # 3: approving this one fails to send — try Send (send failed)
        "subject": "Change my delivery address [send fails]",
        "customer": "chen.demo@example.test", "name": "Chen (demo)",
        "message": "Please send order DEMO-3003 to my office instead.",
        "draft": "Hi Chen,\n\nWe've updated the delivery address for DEMO-3003 to your office.\n\nBest regards,\nDemo Support",
        "fail_send": True,
    },
    {   # 4: an angry complaint — try Escalate (webhook) or Open case (api)
        "subject": "Third time asking — nobody replies!",
        "customer": "dana.demo@example.test", "name": "Dana (demo)",
        "message": "I have written three times about order DEMO-4004 and nobody answers. I want to speak to a manager.",
        "draft": "Hi Dana,\n\nI'm sorry you've had to chase us. I've passed this to a team lead, who will call you today.\n\nBest regards,\nDemo Support",
    },
    {   # 5: off-topic draft — try Reject with a reason (relevance / near miss)
        "subject": "Do you sell gift cards?",
        "customer": "eli.demo@example.test", "name": "Eli (demo)",
        "message": "Do you sell gift cards, and can I send one by email?",
        "draft": "Hi Eli,\n\nOur store opening hours are 9am to 6pm, Monday to Saturday.\n\nBest regards,\nDemo Support",
    },
]

OPTIONS = ["approve", "edit_and_send", "regenerate", "reject", "escalate", "open_case", "email_team"]


def _key(approval_id: str) -> str:
    return f"demo:approval:{approval_id}"


class ReviewActionsDemo(Agent):
    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        payload = req.payload or {}
        if payload.get("invocation_type") == "on_decision":
            return await self._on_decision(req, ctx, payload)

        if payload.get("crash"):
            await ctx.log.error("demo: crash requested — this run fails on purpose")
            raise RuntimeError("Simulated agent failure (demo crash)")

        case = await self._pick_case(ctx, payload)
        return await self._submit(req, ctx, case, case["draft"])

    async def _pick_case(self, ctx: AgentContext, payload: dict) -> dict:
        if payload.get("subject") or payload.get("message"):
            return {
                "subject":   payload.get("subject") or "Demo ticket",
                "customer":  payload.get("customer") or "someone.demo@example.test",
                "name":      payload.get("name") or "Demo customer",
                "message":   payload.get("message") or "",
                "draft":     payload.get("draft") or "Hi,\n\nThanks for your message.\n\nDemo Support",
                "fail_send": bool(payload.get("fail_send")),
            }
        if isinstance(payload.get("case"), int) and 1 <= payload["case"] <= len(CASES):
            index = payload["case"] - 1
        else:
            index = int(await ctx.state.get("demo:next") or 0) % len(CASES)
            await ctx.state.set("demo:next", index + 1)
        case = dict(CASES[index])
        if payload.get("fail_send"):
            case["fail_send"] = True
        return case

    async def _submit(self, req: AgentRequest, ctx: AgentContext, case: dict, draft: str,
                      parent_approval_id: str | None = None, redraft_count: int = 0) -> AgentResponse:
        decision = await ctx.human.request(
            kind="demo-draft-reply",
            tier="T1",
            options=OPTIONS,
            summary=f"Draft reply for “{case['subject']}”",
            detail={
                "subject":       case["subject"],
                "to":            case["customer"],
                "to_name":       case["name"],
                "original_body": case["message"],
                "content_md":    draft,
                "demo_case":     "send fails on approve" if case.get("fail_send") else None,
            },
            submitter_role="AgentOperator",
            invocation_id=req.invocation_id,
            parent_approval_id=parent_approval_id,
        )
        await ctx.state.set(_key(decision.approval_id),
                            {"case": case, "draft": draft, "redrafts": redraft_count})
        await ctx.log.info(f"demo: draft submitted approval={decision.approval_id} subject={case['subject']!r}")
        return AgentResponse(
            content=draft,
            structured={"next": "wait_for_human", "approval_id": decision.approval_id, "status": decision.status},
        )

    async def _on_decision(self, req: AgentRequest, ctx: AgentContext, payload: dict) -> AgentResponse:
        approval_id = payload.get("approval_id") or ""
        decision = payload.get("decision")
        reason = payload.get("reason") or ""
        inputs = payload.get("inputs") or {}
        stash = await ctx.state.get(_key(approval_id)) or {}
        case = stash.get("case") or {}
        draft = stash.get("draft") or ""
        await ctx.log.info(f"demo: decision={decision} approval={approval_id}")

        if decision == "regenerate":
            n = int(stash.get("redrafts") or 0) + 1
            new_draft = f"{draft}\n\n(Redraft {n}, following the note: {reason or 'no note'})"
            return await self._submit(req, ctx, case, new_draft, parent_approval_id=approval_id, redraft_count=n)

        if decision in ("approve", "edit_and_send"):
            body = inputs.get("revised_reply") or draft
            if case.get("fail_send"):
                await ctx.log.error("demo: simulated send failure")
                return AgentResponse(
                    content="Send failed (simulated by the demo agent).",
                    structured={"next": "complete", "outcome": "rejected", "reason": "simulated_send_failure"},
                )
            return AgentResponse(
                content=f"Reply 'sent' to {case.get('customer', 'the customer')} (demo — nothing leaves this machine).",
                structured={"next": "complete", "outcome": "sent", "body_sent": body,
                            "edited": bool(inputs.get("revised_reply"))},
            )

        # reject, or any other key: nothing to send.
        return AgentResponse(content=f"Decision '{decision}' recorded; nothing sent.",
                             structured={"next": "complete", "outcome": decision or "none"})


if __name__ == "__main__":
    run(ReviewActionsDemo())
