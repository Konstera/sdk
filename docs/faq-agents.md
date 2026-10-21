# Agent author FAQ

Short answers for people building agents. For field details see the [manifest reference](manifest-reference.md); for a first agent see [getting started](getting-started.md).

## Building

### Which language can I use?

| Option | Status |
|---|---|
| Python SDK (`konstera_sdk`, `python/`) | The most complete. Has `ctx.capability` and `req.config`. Use it unless you have a reason not to. |
| .NET SDK (`Konstera.Sdk`, `dotnet/`) | Has logging, LLM, state, vector, credentials, cost, tools, agents, artifacts, approvals, rules and connectors. **No `Capability` service and no `config` on `AgentRequest` yet.** |
| Any other language | No SDK. You would implement the HTTP contract below and the MCP client back to the platform yourself. |

### What must my image expose?

An HTTP server on `runtime.port` with:

| Route | Purpose |
|---|---|
| `GET` on `runtime.healthPath` | Readiness. Return 200 when ready. |
| `POST /invoke` | One invocation. |

The SDKs serve `GET /health`, `GET /describe` and `POST /invoke` on port 8080, so set `"port": 8080` and `"healthPath": "/health"`.

`/invoke` receives:

```json
{ "invocationId": "…", "input": "…", "payload": { }, "config": { } }
```

and returns:

```json
{ "content": "…", "structured": { }, "toolCalls": [] }
```

The platform sets these environment variables in the container; the SDK reads them: `KONSTERA_KERNEL_MCP_URL`, `KONSTERA_TENANT_ID`, `KONSTERA_AGENT_INSTANCE_ID`, `KONSTERA_AGENT_ID`, `KONSTERA_AGENT_VERSION`.

### How does my agent call an LLM?

Declare a purpose in `llmRequirements`, then ask by purpose:

```python
result = await ctx.llm.complete(prompt, purpose="drafter", system="You are concise.", max_tokens=500)
print(result.content, result.model, result.cost_usd)
```

The tenant picks the model for each purpose. Your agent never sees an API key. Cost is recorded for you. `model="..."` also works, but it bypasses the tenant's choice; prefer `purpose`.

### How does my agent call another system (orders, tickets, email…)?

Declare a capability in `capabilities.needs` and call it by name:

```python
orders = await ctx.capability.call("orders.lookup_by_email", email=email)
```

The tenant binds the capability to one of its connections. The response has the same shape whatever system is behind it, so the same code works for every tenant.

`ctx.connector.call(alias, method, args)` also exists. It calls a granted connection directly, with a vendor-specific method. Prefer capabilities.

### Required or optional capability: which should I use?

- **Required** (`"required": true`, the default): your agent cannot do its job without it. The portal flags it on **Bindings** until it is bound.
- **Optional** (`"required": false`): the agent works without it. Check before calling:

```python
if await ctx.capability.available("tickets.update_status"):
    await ctx.capability.call("tickets.update_status", ...)
```

Panel capabilities (`review_context_panels`) should usually be optional.

### Why is my capability "not bound"?

`ctx.capability.call()` raises `CapabilityUnbound` when this agent has no binding for that name. Check:

1. Is it bound on the agent's **Bindings › Step 2 · Data & tools**? Bindings are per deployed agent.
2. Does the tenant have a connection that serves it? Connections are set up under **Integrations › Connections**.
3. Is the name spelt exactly as in the platform's capability catalogue? The schema checks only the format, so a misspelt name uploads but can never be bound.

`CapabilityUpstreamFailed` is different: the binding exists, but the connected system failed.

### How do I read per-agent settings?

Declare them in `config` (a JSON Schema). The portal shows a form under **Bindings › Step 3 · Instance configuration**. Values arrive in `req.config`, which holds only what someone set:

```python
tone = req.config.get("tone", "friendly")
```

### How is my agent started on a schedule or by a webhook?

Set up schedules and webhooks on the agent's **Triggers** tab. A schedule can carry an input and a JSON payload. Use a field in the payload to tell run kinds apart, as the platform does with `invocation_type: "on_decision"`.

## Reviewers and the Inbox

### How do I put a draft in front of a reviewer?

Call `ctx.human.request` with `tier="T1"` and the invocation id:

```python
approval = await ctx.human.request(
    kind="draft-reply",
    tier="T1",
    summary="Draft reply for order 1001",
    detail={
        "subject": "Where is my order?",
        "content_md": draft,                 # the draft the reviewer approves
        "original_body": customer_message,   # optional: the message it answers
        "to": "customer@example.com",
        "to_name": "Ada",
    },
    options=["approve", "edit_and_send", "regenerate", "reject"],
    invocation_id=req.invocation_id,
)
```

What the Inbox uses from `detail`:

| Key | Shown as |
|---|---|
| `content_md` (or `drafted_reply`) | The draft. Without either, the summary plus the detail as JSON. |
| `subject` | Thread subject. Without it, the summary. |
| `original_body` | The inbound message the draft answers. |
| `to`, `to_name` | Sender of that inbound message. |

Tiers:

| Tier | Result |
|---|---|
| `T0` | Blocked at once. |
| `T1` | Pending. Opens an Inbox thread. |
| `T2`, `T3` | Approved at once by the platform; kept for audit. |

### My draft did not appear in the Inbox. Why?

- The tier is not `T1`. Only pending approvals open an Inbox thread.
- `invocation_id` was not passed. The platform needs it to open the thread.
- Outside the platform (direct-run mode), `ctx.human.request` raises an error instead.

### How do I add my own Inbox buttons?

Declare them in `reviewActions` **and** list their keys in `options` when you call `ctx.human.request`. The Inbox shows only declared actions that the approval offers. Use `shortLabel` (max 20 characters) for the button text. See [reviewActions](manifest-reference.md#reviewactions).

### How do I make a button that calls a webhook or an API?

Give the action `"actionType": "webhook"` (or `"api"`), a `target` slot and a `payload` template:

```json
{ "key": "escalate", "label": "Escalate to Tier 2", "shortLabel": "Escalate", "kind": "neutral",
  "icon": "escalate", "actionType": "webhook", "target": "escalation",
  "payload": { "approval": "{{ approval.id }}", "draft": "{{ draft.content }}" } }
```

The tenant binds the `escalation` slot to an HTTP endpoint connection on **Bindings › Action targets**. The URL and secrets live there, never in your manifest. Until it is bound, the button is disabled. The platform sends the request; your agent is not invoked.

For email, use `"actionType": "email"`; the payload must give `to`, `subject` and `body`.

### How does the reviewer's decision reach my agent?

For `agent` actions (the default), the platform invokes your agent again with this payload:

```json
{
  "invocation_type": "on_decision",
  "approval_id": "…",
  "decision": "edit_and_send",
  "reason": "…",
  "actor_id": "…",
  "actor_role": "…",
  "inputs": { "revised_reply": "…" }
}
```

- `decision` is the action key.
- `reason` is the reviewer's note, or `null`.
- `inputs` holds the `requiresInput` values. An edited draft arrives as `inputs.revised_reply`.

Save what you need under the approval id when you submit (for example with `ctx.state`), then load it in the `on_decision` run. If that run fails, the platform records the send step as failed.

For a redraft, submit a new approval and pass `parent_approval_id=<old approval id>` so both count as one draft chain.

### How do I add context panels beside the draft, and why might one not show?

Declare up to four panels in `review_context_panels` (slots `header`, `primary`, `secondary`, `footer`), each fed by a capability you also list in `capabilities.needs`. See [review_context_panels](manifest-reference.md#review_context_panels).

A panel does not show when:

- its capability is not bound for this agent;
- the tenant set a per-agent panel override, which replaces your manifest panels entirely.

The upload is rejected if two panels share a slot, or a panel's capability is not in `capabilities.needs`.

## Versions and variants

### How do versions work? Can two versions coexist?

- Each upload is stored per `id` + `version`. Uploading the same `id` and `version` again replaces that version's manifest.
- The Catalog keeps every version. You pick one when you deploy.
- Two deployed agents can run different versions of the same package side by side.
- To move a deployed agent to another uploaded version, use **Technical details › Version history** (**Roll back**). The running container is stopped; the next invocation uses the new image.

Bump `version` and use a new image tag for every code change.

### Can one image serve two variants (for example retail and SaaS)?

Yes. Write one manifest per variant with its own `id`, all pointing at the same `runtime.image`. Each manifest declares only the capabilities, settings, LLM purposes and panels that variant uses. Your code branches on what is bound (`ctx.capability.available(...)`), not on the variant name.

The customer service reference agent does this:

| Manifest | `id` | Differences |
|---|---|---|
| Retail | `io.konstera.customer-service-agent-retail` | Order capabilities required; recent orders and returns panels. |
| SaaS | `io.konstera.customer-service-agent-saas` | No order capabilities; adds email sending and internal investigation capabilities. |

Keep the versions in step: when the image tag changes, update every manifest that uses it.

## Testing

### How do I test locally?

1. **Unit tests.** `Agent` has no transport code. Call `await agent.handle(request, ctx)` with an `AgentRequest` and a context whose services you replace with fakes.
2. **Container.** Run the image and call it:

   ```bash
   docker run --rm -p 8080:8080 my-agent:0.1.0
   curl http://localhost:8080/health
   curl -X POST http://localhost:8080/invoke -H "Content-Type: application/json" \
     -d '{"invocationId": "local-1", "input": "hi", "payload": {}}'
   ```

   Without the platform, `ctx.log` calls are skipped and calls that need a result (state, LLM, approvals, capabilities) raise an error.
3. **On a Konstera instance.** Deploy to a test instance and use the **Test** tab. What you type in **Payload (JSON)** arrives as `req.payload`; `req.input` is empty.

### How do I validate a manifest?

Validate it against `schemas/agent-manifest.v3.json` with Python `jsonschema` (Draft 2020-12). The script is in [getting started](getting-started.md#5-validate-the-manifest-locally). The upload also runs a few extra checks the schema cannot express; see [checks beyond the schema](manifest-reference.md#checks-beyond-the-schema).

### Where do I see what my agent did?

The agent's **Runs** tab (and **Activity › Runs**) lists every invocation, including `on_decision` runs and Test runs. `ctx.log.info/warn/error` lines are attached to the run. If you declare `outputSchema` and `uiHints`, the run page shows `structured` as formatted output.

## Data

### What data does my agent store?

- **Your state.** `ctx.state` is a key-value store per deployed agent, scoped to the tenant. Values are JSON. Use it for working data such as a draft waiting for review, and delete it (`ctx.state.delete(key)`) when the work is finished.
- **Business data stays in the source system.** Read it through capabilities when you need it. Do not keep your own copy of tickets, orders or emails.
- **What the platform keeps.** By default, run history keeps the shape of inputs and outputs (keys, sizes, hashes), not their content. Content in a pending approval's `detail` is a working copy; the platform removes it after the draft is final and the tenant's retention period has passed. The decision, the draft and the sent text are kept as evidence.

### Where do secrets go?

Not in the manifest and not in the image. LLM provider keys are held by the tenant on the platform. Connection credentials belong to the tenant's connections. Your agent reaches both through `ctx.llm` and `ctx.capability`.
