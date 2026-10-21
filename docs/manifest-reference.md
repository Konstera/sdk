# Manifest reference

The manifest is a JSON file that describes your agent to the platform. You upload it in **Agents › Catalog**. The authoritative definition is [`schemas/agent-manifest.v3.json`](../schemas/agent-manifest.v3.json); this page explains each section and where it shows up in the portal.

Rules that apply everywhere:

- Field names are case-sensitive. Most are camelCase; `review_context_panels` is snake_case.
- Unknown fields are rejected (`additionalProperties: false`) at the top level and inside most sections.
- Required at the top level: `manifestVersion`, `id`, `name`, `version`, `runtime`.

Examples on this page come from the reference agents and the [review actions demo](examples/review-actions-demo/).

## Contents

- [Identity](#identity)
- [runtime](#runtime)
- [kernelServices](#kernelservices)
- [permissions](#permissions)
- [capabilities.needs](#capabilitiesneeds)
- [llmRequirements](#llmrequirements)
- [config](#config)
- [reviewActions](#reviewactions)
- [review_context_panels](#review_context_panels)
- [outputSchema and uiHints](#outputschema-and-uihints)
- [Other fields](#other-fields)
- [connectionRequirements (deprecated)](#connectionrequirements-deprecated)
- [Checks beyond the schema](#checks-beyond-the-schema)

## Identity

| Field | Type | Rules |
|---|---|---|
| `$schema` | string (URI) | Optional. |
| `manifestVersion` | number | Required. Must be `3`. |
| `id` | string | Required. Reverse-DNS, lower case: pattern `^[a-z0-9]+(\.[a-z0-9-]+)+$`, e.g. `com.example.hello-agent`. |
| `name` | string | Required. 1–200 characters. |
| `version` | string | Required. SemVer 2.0, e.g. `0.5.2` or `1.0.0-beta.1`. |
| `description` | string | Up to 4000 characters. |
| `icon` | string | Emoji or absolute image URL, up to 512 characters. |
| `license` | string | Up to 100 characters. |
| `groupName` | string | Up to 100 characters. Groups the agent in the portal (e.g. `Finance`). |
| `author` | object | `name`, `email`, `url`. |

```json
{
  "manifestVersion": 3,
  "id": "io.konstera.customer-service-agent-retail",
  "name": "Customer Service — Retail",
  "version": "0.5.2",
  "icon": "🎧",
  "groupName": "Customer Success"
}
```

**In the portal:** the Catalog lists one row per `id`, with each uploaded `version`. The name, icon and description appear on the Catalog and the agent's pages.

## runtime

How the platform runs your container. Required.

| Field | Type | Rules |
|---|---|---|
| `kind` | enum | Required. `container`, `mcp-stdio`, `mcp-http`. Use `container`; it is the only kind the platform runs today. |
| `image` | string | Required. OCI image reference the platform pulls. |
| `port` | integer | Required. 1–65535. The SDKs listen on `8080`. |
| `healthPath` | string | Required. Starts with `/`. The SDKs serve `/health`. |
| `timeoutSeconds` | integer | Required. 1–3600. Limit for one invocation. |
| `memoryMi` | integer | 32–32768. Memory cap in MiB. Platform default when omitted. |
| `cpuMillis` | integer | 50–32000. CPU cap in millicores (1000 = 1 core). |
| `pidsLimit` | integer | 10–10000. Max processes/threads. |

```json
"runtime": {
  "kind": "container",
  "image": "konstera/customer-service-agent:0.5.2",
  "port": 8080,
  "healthPath": "/health",
  "timeoutSeconds": 240,
  "memoryMi": 512,
  "cpuMillis": 500
}
```

**In the portal:** **Technical details › Package details** (image, port, health path, timeout).

## kernelServices

The platform services your agent calls. **Informational:** the platform checks access per call, not from this list. It helps the portal describe the agent.

| Field | Type |
|---|---|
| `required` | array of service names |
| `optional` | array of service names |
| `notes` | string |

Service names: `log`, `llm`, `state`, `vector`, `credentials`, `cost`, `tool`, `agents`, `artifact`, `human`, `rule`, `connector`, `prompt`, `capability`.

```json
"kernelServices": {
  "required": ["log", "llm", "capability"],
  "optional": ["state", "cost"]
}
```

## permissions

| Field | Type | Meaning (from the schema) |
|---|---|---|
| `network` | array of strings | Allowed egress hosts. Empty means no egress beyond the platform network. |
| `filesystem` | enum | `none` (default), `readonly`, `read-write`. |
| `callableAgents` | array of strings | Reverse-DNS ids of other agents this one may invoke. |

```json
"permissions": { "network": [], "filesystem": "none", "callableAgents": [] }
```

Prefer `capabilities.needs` over direct network access: the platform then handles credentials, auditing and the connection to the outside system.

## capabilities.needs

The data and tools your agent uses, named by **capability**, not by vendor. A tenant binds each capability to one of its connections. Your code stays the same whatever system is behind it.

| Field | Type | Rules |
|---|---|---|
| `name` | string | Required. Dotted lower-case key, e.g. `orders.lookup_by_email`. Pattern `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`. |
| `required` | boolean | Default `true`. |
| `reason` | string | Up to 500 characters. Shown to the person who binds it. |

```json
"capabilities": {
  "needs": [
    { "name": "knowledge.search",       "required": true,  "reason": "KB-first: every reply is grounded in policy articles" },
    { "name": "tickets.reply",          "required": true,  "reason": "Post the approved reply back on the source ticket" },
    { "name": "orders.lookup_by_email", "required": false, "reason": "Retail installs bind this so replies can cite order status; SaaS installs leave it unbound" }
  ]
}
```

**Names must exist in the platform's capability catalogue.** The schema checks only the format, so a misspelt name uploads but can never be bound. Copy names from the reference agents, or list the catalogue through your instance's API (`GET /api/capabilities`).

**Required vs optional:**

| | Required (`true` or omitted) | Optional (`false`) |
|---|---|---|
| Portal | Flagged as missing on **Bindings** until bound. | Listed; may stay unbound. |
| Your code | Call it directly. | Check `await ctx.capability.available(name)` first. |

**In your code:**

```python
if await ctx.capability.available("orders.lookup_by_email"):
    orders = await ctx.capability.call("orders.lookup_by_email", email=email)
```

`ctx.capability.call()` raises `CapabilityUnbound` when there is no binding, and `CapabilityUpstreamFailed` when the connected system fails.

**In the portal:** **Bindings › Connections this agent uses** (summary) and **Bindings › Step 2 · Data & tools** (binding).

## llmRequirements

The LLM **purposes** your agent uses. The tenant chooses the actual model for each purpose. Your code asks by purpose.

| Field | Type | Rules |
|---|---|---|
| `purpose` | string | Required. Pattern `^[a-z][a-z0-9_-]*$`, e.g. `drafter`. |
| `suggestedModel` | string | Hint shown when binding. |
| `maxTokens` | integer | ≥ 1. |
| `supportsStreaming` | boolean | Default `false`. |
| `description` | string | What the purpose is for. |

```json
"llmRequirements": [
  {
    "purpose": "drafter",
    "suggestedModel": "claude-haiku-4-5-20251001",
    "maxTokens": 2048,
    "description": "Drafts a human-tone reply to the customer, grounded in KB snippets + order context."
  }
]
```

**In your code:**

```python
result = await ctx.llm.complete("Write a short greeting.", purpose="drafter", max_tokens=200)
text = result.content
```

The platform resolves the model, uses the tenant's provider key and records the cost. Your agent never handles LLM API keys.

**In the portal:** tenant defaults on **Integrations › Models**; per-agent overrides on **Bindings › Step 1 · Models**. A purpose with no model fails at run time.

## config

A JSON Schema for per-agent settings. The portal renders a form from it, and the values reach your agent as `req.config`.

Supported property types in the form:

| Type | Form control |
|---|---|
| `string` | Text field |
| `string` with `enum` | Drop-down |
| `integer`, `number` | Number field |
| `boolean` | True/false choice |

The form also uses `default` (shown as the placeholder) and `description` (help text).

```json
"config": {
  "type": "object",
  "properties": {
    "tone":     { "type": "string", "enum": ["formal", "friendly", "casual"], "default": "friendly", "description": "How the drafted reply should read." },
    "kb_top_k": { "type": "integer", "minimum": 1, "maximum": 20, "default": 4, "description": "How many KB articles to fetch for grounding." },
    "close_on_reply": { "type": "boolean", "default": true, "description": "Mark the ticket resolved after a successful reply." }
  }
}
```

`req.config` holds only the values someone has set. Apply your own defaults:

```python
tone = req.config.get("tone", "friendly")
```

**In the portal:** **Bindings › Step 3 · Instance configuration** (shown only when `config` has properties).

## reviewActions

The buttons a reviewer sees in the **Inbox** for drafts your agent submits with `ctx.human.request(...)`.

| Field | Type | Rules |
|---|---|---|
| `key` | string | Required. Pattern `^[a-z][a-z0-9_]*$`. Unique within the manifest. |
| `label` | string | Required. 1–100 characters. Tooltip when `shortLabel` is set. |
| `kind` | enum | Required. `positive`, `negative`, `neutral`. |
| `shortLabel` | string | 1–20 characters. The button text. |
| `icon` | enum | `send`, `edit`, `x`, `refresh`, `escalate`, `mail`, `webhook`, `api`, `check`, `flag`. |
| `confirm` | string | 1–200 characters. A question asked before the action runs. |
| `reasonRequired` | boolean | Default `false`. The reviewer must give a reason. |
| `requiresInput` | array | Fields the reviewer fills in. Each: `field`, `type` (`string`, `number`, `integer`, `boolean`), optional `min`, `max`, `label`. |
| `actionType` | enum | `agent` (default), `email`, `webhook`, `api`. |
| `target` | string | Slot name, pattern `^[a-z][a-z0-9_]{0,63}$`. Required for `email`, `webhook`, `api`. |
| `payload` | object | JSON body template for `email`, `webhook`, `api`. |

### Which buttons appear

- The Inbox shows your declared actions **that are also in the approval's `options`**. Pass the keys in `ctx.human.request(options=[...])`.
- With no `options`, an approval offers `approve`, `reject` and `rework`.
- If the agent declares no actions, or none the approval offers, the Inbox shows its four default buttons.

### Built-in keys

These `agent` keys keep the Inbox's own screens:

| Key | Reviewer experience | What reaches your agent |
|---|---|---|
| `approve` | Send the draft as is | `decision: "approve"` |
| `edit_and_send` | Edit the draft, then send | `decision: "edit_and_send"`, edited text in `inputs.revised_reply` |
| `regenerate` (or `rework`) | Ask for a new draft with a note | `decision: "regenerate"`, note in `reason` |
| `reject` | Reject | `decision: "reject"`, `reason` |

Any other `agent` key is recorded with its key and sent to your agent the same way.

### Action types

| `actionType` | What happens on click | `target` is bound to |
|---|---|---|
| `agent` | The platform invokes your agent with `invocation_type: "on_decision"`. | — |
| `email` | The platform sends an email. Your agent is **not** invoked. | An email connection. If the slot is unbound, the agent's own `email.send` binding is used. |
| `webhook` | The platform POSTs a signed JSON body. Your agent is **not** invoked. | An HTTP endpoint connection. |
| `api` | The platform POSTs an authenticated JSON body. Your agent is **not** invoked. | An HTTP endpoint connection. |

URLs, secrets and signing keys live in the tenant's connection, never in the manifest. An unbound `webhook` or `api` slot disables its button.

If an `email`, `webhook` or `api` dispatch fails, the decision stays recorded, the dispatch is marked failed, and the reviewer gets a **Retry** button.

### Payload templates

String values in `payload` may contain `{{ var }}`. Allowed variables:

| Variable | Value |
|---|---|
| `approval.id`, `approval.kind` | The approval |
| `draft.content` | The draft text |
| `detail.<key>` | A top-level value from the `detail` you passed to `ctx.human.request` |
| `thread.id`, `thread.subject` | The Inbox thread |
| `inputs.<field>` | A reviewer input; the field must be declared in `requiresInput` |
| `reviewer.id` | The reviewer |

No other expressions are allowed. A string that is exactly one placeholder keeps the value's JSON type. An `email` payload must give `to`, `subject` and `body`.

What the receiving endpoint gets (`webhook` and `api`):

- A JSON POST to the connection's base URL plus one of its allowed paths. HTTPS only.
- `X-Konstera-Idempotency-Key`: the same on every retry, also sent as `idempotencyKey` in the body. De-duplicate on it.
- `X-Konstera-Delivery`: one id per attempt.
- When the connection has a signing secret: `X-Konstera-Signature: sha256=<hex>` (HMAC-SHA256 of `<timestamp>.<body>`) and `X-Konstera-Timestamp` (Unix seconds).
- When the connection has an auth header value: `Authorization`.

### Example

From the review actions demo:

```json
"reviewActions": [
  { "key": "approve", "label": "Approve & send the draft as it is", "shortLabel": "Send", "kind": "positive", "icon": "send" },
  { "key": "edit_and_send", "label": "Edit the draft, then send", "shortLabel": "Edit", "kind": "positive", "icon": "edit",
    "requiresInput": [{ "field": "revised_reply", "type": "string", "label": "Revised reply" }] },
  { "key": "regenerate", "label": "Ask the agent for a new draft, with a note", "shortLabel": "Redraft", "kind": "neutral", "icon": "refresh",
    "reasonRequired": true },
  { "key": "reject", "label": "Reject — do not send", "shortLabel": "Reject", "kind": "negative", "icon": "x" },
  { "key": "escalate", "label": "Escalate to Tier 2 through the escalation webhook", "shortLabel": "Escalate", "kind": "neutral",
    "icon": "escalate", "actionType": "webhook", "target": "escalation",
    "confirm": "Escalate this ticket to Tier 2?",
    "requiresInput": [{ "field": "reason", "type": "string", "label": "Why escalate?" }],
    "payload": { "approval": "{{ approval.id }}", "subject": "{{ thread.subject }}", "customer": "{{ detail.to }}",
                 "draft": "{{ draft.content }}", "reason": "{{ inputs.reason }}", "by": "{{ reviewer.id }}" } },
  { "key": "email_team", "label": "Email the draft to the support team lead", "shortLabel": "Email team", "kind": "neutral",
    "icon": "mail", "actionType": "email", "target": "team_mail",
    "payload": { "to": "team-lead@example.test", "subject": "FYI: {{ thread.subject }}", "body": "{{ draft.content }}" } }
]
```

**In the portal:** buttons in **Inbox**; target slots on **Bindings › Action targets** (shown only when the agent declares `email`, `webhook` or `api` actions).

## review_context_panels

Read-only panels beside the draft in the **Inbox**, so the reviewer sees context (customer, orders, previous tickets) without leaving the page.

- Four fixed slots: `header`, `primary`, `secondary`, `footer`. At most one panel per slot, so at most four panels.
- Six widgets: `identity_card`, `metric_tile`, `list`, `timeseries`, `kv_grid`, `markdown_block`.
- Each panel is fed by one capability. That capability **must be declared in `capabilities.needs`**.

| Field | Type | Rules |
|---|---|---|
| `slot` | enum | Required. `header`, `primary`, `secondary`, `footer`. |
| `widget` | enum | Required. One of the six widgets. |
| `title` | string | 1–100 characters. |
| `source.capability` | string | Required. Capability key. |
| `source.args` | object | Arguments for the capability. Strings may use `{{ thread.* }}`, `{{ widget.<slot>.* }}` or `{{ tenant.* }}`. |

`{{ widget.header.id }}` reuses a value returned by the panel in another slot, as in this example:

```json
"review_context_panels": [
  { "slot": "header", "widget": "identity_card",
    "source": { "capability": "customers.lookup_by_email",
                "args": { "email": "{{ thread.participants.external.0.email }}" } } },
  { "slot": "primary", "widget": "list", "title": "Recent orders",
    "source": { "capability": "customers.recent_orders",
                "args": { "customerId": "{{ widget.header.id }}", "email": "{{ thread.participants.external.0.email }}", "limit": 6 } } },
  { "slot": "secondary", "widget": "list", "title": "Previous tickets",
    "source": { "capability": "customers.recent_tickets",
                "args": { "email": "{{ thread.participants.external.0.email }}", "limit": 6 } } }
]
```

Good to know:

- **A panel is hidden when its capability is not bound** for that agent. Declare panel capabilities as `"required": false` so an install without them still works.
- The data comes from the capability, not from your agent. Your agent does not run when the reviewer opens the panel.
- A tenant can replace an agent's panels with a per-agent override. The override replaces the manifest list entirely; it is not merged. There is no portal editor for overrides yet.

## outputSchema and uiHints

`outputSchema` is a JSON Schema for what your agent returns in `AgentResponse.structured`. `uiHints` tells the portal how to show it on a run's detail page (**Activity › Runs**).

| `uiHints` field | Meaning |
|---|---|
| `heroField` | Top-level field shown prominently. |
| `heroFormat` | Format hint, e.g. `currency:USD`, `percent`, `count`. |
| `heroLabel` | Label for the hero value. |
| `kpiFields` | Dot-paths shown as KPI tiles. |
| `tableFields` | Fields shown as tables. |
| `collapsibleFields` | Fields shown collapsed. |
| `uiComponent` | Name of a bespoke portal component to use instead. |

```json
"uiHints": {
  "heroField": "drafted_reply",
  "heroFormat": "text",
  "heroLabel": "Draft reply",
  "tableFields": ["thread_context"],
  "collapsibleFields": ["context_used", "ticket_id"]
}
```

## Other fields

These are defined in the schema. Their exact effect is not covered in this guide; see the schema for their shape.

| Field | Schema summary |
|---|---|
| `triggers` | Array of `{ kind: "cron", cadence, timezone }`, `{ kind: "webhook", path, hmacRequired }` or `{ kind: "event", subscribesTo }`. |
| `retry` | `maxAttempts` (1–10), `backoff` (`fixed`/`exponential`), `initialDelayMs`, `retryOnCategories`, `noRetryOnCategories`. |
| `errorHandling` | Circuit-breaker settings: `maxConsecutiveFailures`, `circuitCooldownSeconds`, `circuitBackoffMultiplier`, `alertOnCategories`. |
| `observability` | `metrics`, `trace` (`otel`/`none`), `logLevel` (`debug`/`info`/`warn`/`error`). |

Error categories used by `retry` and `errorHandling`: `input_invalid`, `agent_bug`, `agent_timeout`, `dependency_failure`, `credential_missing`, `budget_exceeded`, `platform_bug`, `circuit_open`.

## connectionRequirements (deprecated)

Older agents listed acceptable connection types per purpose. Each item has `purpose` (required, pattern `^[a-z][a-z0-9_-]*$`), `acceptableTypes` (required, at least one string), `grantRequired` (default `true`) and `description`.

Use [`capabilities.needs`](#capabilitiesneeds) instead. The field is kept only so older manifests still validate.

## Checks beyond the schema

At upload, the platform also rejects a manifest when:

- two `reviewActions` share a `key`;
- an `email`, `webhook` or `api` action has no `target`;
- a `payload` uses a variable outside the allowed list, or `inputs.<field>` that `requiresInput` does not declare;
- an `email` action's `payload` lacks `to`, `subject` or `body`;
- two `review_context_panels` use the same `slot`;
- a panel's `source.capability` is not declared in `capabilities.needs`.

Local validation with the JSON Schema does not catch these. See [Getting started › Validate the manifest locally](getting-started.md#5-validate-the-manifest-locally).
