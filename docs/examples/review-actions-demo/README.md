# Review actions demo

> **Demo only.** This agent uses made-up customers, orders and addresses. It calls no LLM and sends nothing to real people. Do not deploy it for a real tenant.

A small Python agent that puts canned drafts in the **Inbox**, so you can try every review action type:

| Button | `actionType` | What happens |
|---|---|---|
| Send, Edit, Redraft, Reject | `agent` | The decision comes back to the agent as `invocation_type: "on_decision"`. |
| Escalate | `webhook` | The platform POSTs to the connection bound to the `escalation` slot. |
| Open case | `api` | The platform POSTs to the connection bound to the `case_api` slot. |
| Email team | `email` | The platform sends an email through the `team_mail` slot, or the agent's `email.send` binding. |

## Files

| File | What it shows |
|---|---|
| `manifest.json` | `reviewActions` with every action type, `shortLabel`, `icon`, `confirm`, `requiresInput`, `reasonRequired` and payload templates. |
| `main.py` | `ctx.human.request` with `options`, the `detail` keys the Inbox reads, `ctx.state` to keep the draft, and the `on_decision` branch (including redrafts with `parent_approval_id`). |
| `Dockerfile` | A two-stage build that installs the SDK from a clone of this repository. |

## Try it

1. Build the image (see the comment at the top of `Dockerfile`), push it, and set `runtime.image` in `manifest.json` to the pushed reference.
2. Upload `manifest.json` in **Agents › Catalog** and deploy it.
3. Optional: on **Bindings › Action targets**, bind `escalation` and `case_api` to HTTP endpoint connections, and `team_mail` to an email connection. Unbound webhook and API buttons stay disabled.
4. **Start agent**, then on the **Test** tab run one of these payloads:

| Payload | Result |
|---|---|
| `{}` | The next canned case. |
| `{"case": 1}` … `{"case": 5}` | A specific case. |
| `{"fail_send": true}` | Approving the draft reports a failed send. |
| `{"crash": true}` | The run itself fails. |

5. Open **Inbox**, pick the draft and try the buttons. Each decision shows as a new run on the **Runs** tab.
