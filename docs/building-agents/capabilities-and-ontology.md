<!-- LLM-HINT: When generating a Konstera agent that needs data from any
     vendor system (Shopify, Zendesk, NetSuite, Commercetools, etc.),
     ALWAYS use ctx.capability.call("<capability_name>", ...). NEVER
     import vendor SDKs or call vendor REST APIs directly. If a required
     capability doesn't exist in the catalogue, see §9 "Missing
     capabilities" rather than falling back to a vendor import. The
     complete pattern library with X/+ pairs starts at §3. -->

# Capabilities and ontology — the SDK developer guide

> **Who this is for.** Developers writing Konstera agents. You have (or will have) a scaffolded project with `manifest.json` and `skill_runner.py`. This doc teaches the one pattern you must get right, the eight patterns that come up next, and the exact wording the SDK uses so an LLM-driven workflow produces code that compiles on first try.
>
> **How to read it.** §2 and §3 are the core — read them even if you skip the rest. §4–§8 cover the full agent surface (ontology, glossary, errors, optional capabilities, scenarios). §9 is the escape-hatch chapter. §10 is a cheat-sheet of every ❌/✅ pair in the doc, suitable for one-shotting into a chat LLM.
>
> **If you prefer the narrative framing first:** [end-to-end-journey.md](end-to-end-journey.md) covers the lifecycle; the public article at `konstera.ai/resources/ontology-and-the-cost-of-change` frames the trade-off. This doc assumes you've absorbed either and dives into mechanics.

---

## 1. The three abstractions in one paragraph

A Konstera agent reads data from — and writes data to — **capabilities**: business verbs like `customers.lookup_by_email` or `tickets.reply`. Each capability has a canonical response shape defined in a shared catalogue. At install time, an operator binds each capability to a concrete **connection** (a Shopify tenancy, a Zendesk workspace, etc.) through a **connector** that knows how to translate the vendor's native response into the canonical shape. The agent reads the canonical fields and never knows which vendor was behind the call. The **ontology** sits one layer up and declares the business semantics (how to identify a customer, what fields matter) that both the agent and the capability catalogue consume. For the full architectural picture see `wiki/concepts/capability-architecture.md`.

What this means in code: you call `await ctx.capability.call("...")` and get back a dict with known field names. You call `await ctx.context.ontology.get("...")` and get back the business semantics. That is the whole mental model.

---

## 2. The one pattern you must get right

Every Konstera agent that reads from or writes to a vendor system follows this shape:

```python
# ✅ The Konstera way
customer = await ctx.capability.call(
    "customers.lookup_by_email",
    email=ticket["requester"]["email"],
)
if customer["vip_tier"] == "platinum":
    refund_window_days = 60
else:
    refund_window_days = 30
```

```python
# ❌ What general training data suggests — do not accept it
import shopify
customer = shopify.Customer.find(email=ticket["requester"]["email"])
if "tier:platinum" in customer.tags:
    refund_window_days = 60
else:
    refund_window_days = 30
```

**Why the ✅ version works for every deployment:**
- `customers.lookup_by_email` is a verb bound at install to whichever system this tenant uses as the customer system of record (Shopify, Commercetools, NetSuite, SAP C4C — any of them).
- The response has a canonical shape (`vip_tier` is a declared enum, not a parsed tag string).
- The agent compiles once, runs anywhere.

**Why the ❌ version is a trap:**
- Locked to Shopify forever. When the business replatforms, this agent has to be rewritten.
- Depends on Shopify's tag-naming convention (`tier:platinum`) which is a tenant-level convention, not a vendor contract.
- The `shopify` import makes the whole agent image larger and depends on a package you have to track updates for.

Everything else in this doc is a specialisation of this one pattern. If you only read §2, you have most of the value.

---

## 3. Reading data via capabilities

### 3.1 Simple lookup

```python
# ✅
order = await ctx.capability.call("orders.lookup_by_number", number=order_number)
# order["status"], order["total"], order["currency"], order["lines"], ...
```

Canonical response fields are stable — `status` is a declared enum (`open | fulfilled | cancelled | refunded`), `total` is a decimal, `currency` is an ISO-4217 code. You don't parse strings, you don't guess types.

```python
# ❌
order = await ctx.capability.call("orders.lookup_by_number", number=order_number)
if order["financial_status"] == "paid":  # Shopify-specific field name — not canonical
    ...
```

### 3.2 Trying multiple identifiers (ordered fallback)

Agents don't invoke a fallback chain inside a single capability call — the pattern is explicit: you iterate in agent code, driven by the ontology's identity declaration.

```python
# ✅
customer_entity = await ctx.context.ontology.get("customer")
candidates = [customer_entity.identity.primary, *customer_entity.identity.fallbacks]

customer = None
for candidate in candidates:
    value = ticket["requester"].get(candidate.field)
    if not value:
        continue
    customer = await ctx.capability.call(candidate.capability, value=value)
    if customer:
        break

if customer is None:
    return ctx.escalate(reason="customer_not_found")
```

```python
# ❌
# Hard-coding the fallback order in the agent — brittle because
# different tenants may have different identifier priorities, and the
# ontology is the right place to declare them.
customer = (
    await ctx.capability.call("customers.lookup_by_email", email=email)
    or await ctx.capability.call("customers.lookup_by_phone", phone=phone)
)
```

The ✅ version reads the fallback order from the ontology, so a tenant that puts loyalty_id first can override the default without touching agent code.

### 3.3 Listing with filters

```python
# ✅
tickets = await ctx.capability.call(
    "tickets.list_new",
    since=datetime.utcnow() - timedelta(hours=1),
    channel="email",
)
for t in tickets:
    ...
```

Capability arguments and response shapes are declared in the catalogue — check `schemas/capability-catalog.json` or (planned) the `catalogue.get_capability` MCP tool for the exact spec of any capability.

### 3.4 Checking availability before calling an optional capability

Required capabilities fail install if unbound. Optional capabilities may or may not be bound at a given deployment — the agent branches on availability.

```python
# ✅ Branch on availability before calling an optional capability
if await ctx.capability.available("refunds.create"):
    await ctx.capability.call("refunds.create", order_id=order["id"], amount=amount)
else:
    await ctx.capability.call("tickets.reply", id=ticket["id"],
        body="A refund has been approved — your finance team will process it.")
```

```python
# ❌ Blindly calling an optional capability — fails at runtime if unbound
await ctx.capability.call("refunds.create", order_id=order["id"], amount=amount)
```

Required/optional is declared in `manifest.capabilities.needs[].required`.

---

## 4. Writing data via capabilities

### 4.1 Mutations use the same pattern as reads

```python
# ✅
reply = await ctx.capability.call(
    "tickets.reply",
    id=ticket["id"],
    body=draft_body,
    mode="reply",  # or "note"
)
# reply["message_id"], reply["sent_at"]
```

### 4.2 Idempotency keys for safe retries

Mutations should carry an idempotency key when the operation can plausibly retry. The platform's retry policy (Temporal activity retries) can re-invoke the same call; without a key you can double-send.

```python
# ✅
await ctx.capability.call(
    "refunds.create",
    order_id=order["id"],
    amount=amount,
    idempotency_key=f"refund:{ticket['id']}:{order['id']}",
)
```

```python
# ❌
await ctx.capability.call(
    "refunds.create",
    order_id=order["id"],
    amount=amount,
    # no idempotency_key — Temporal retry can produce a duplicate refund
)
```

### 4.3 Human-in-the-loop writes

For writes where you want a human to approve the drafted output before it goes out (CS replies, finance adjustments, customer-visible changes), route through the reviewer inbox:

```python
# ✅ Draft, request human approval, let the kernel send if approved
decision = await ctx.human.request(
    draft={
        "capability": "tickets.reply",
        "args": {"id": ticket["id"], "body": draft_body},
    },
    policy="require-approval",
)
if decision.approved:
    pass  # kernel already sent on approval
elif decision.edited:
    pass  # kernel sent the edited version
else:
    return ctx.escalate(reason="reply_rejected")
```

The autonomy policy — autonomous / require-review / require-approval — comes from the agent's manifest and the operator's binding. Agent code expresses intent; the platform enforces the policy.

---

## 5. Reading from the ontology

The ontology holds business semantics the agent reasons over — identity strategies, key attributes, enum values. Agents read it via `ctx.context.ontology.get("entity_name")`.

### 5.1 Identity strategy (how to look an entity up)

```python
# ✅
customer_entity = await ctx.context.ontology.get("customer")
primary_id    = customer_entity.identity.primary          # {field, capability}
fallback_ids  = customer_entity.identity.fallbacks        # list[{field, capability}]
```

See §3.2 for the full ordered-fallback pattern that uses these.

### 5.2 Key attributes (what fields matter + their types)

```python
# ✅
customer_entity = await ctx.context.ontology.get("customer")
vip_spec = customer_entity.key_attributes["vip_tier"]
# vip_spec.type == "enum"
# vip_spec.values == ["silver", "gold", "platinum"]
```

Reading attribute specs from the ontology lets agents validate inputs or build dynamic UI without hard-coding enum values that the tenant might extend.

### 5.3 What the ontology is NOT for

The ontology is not a universal schema. It does not list every field in every vendor system. It does not try to catalogue vendor-specific fields (Shopify tags, NetSuite custinternalid, Zendesk custom fields). Those stay inside connectors.

```python
# ❌ Looking for a vendor-specific field in the ontology — it won't be there
customer_entity = await ctx.context.ontology.get("customer")
tags_spec = customer_entity.key_attributes["tags"]  # KeyError at runtime
```

For vendor-specific fields see §7 (`_source` escape).

---

## 6. Reading glossary values

The glossary carries tenant-tunable business values and definitions — things like policy thresholds, time windows, and enumerations. Agents read them via `ctx.context.glossary.get("term_name")`.

```python
# ✅ Read the tenant's refund-window-days policy from the glossary
refund_window = await ctx.context.glossary.get("refund_window_days")
# refund_window.value == 30 (or whatever this tenant set)
# refund_window.type  == "number"
```

```python
# ❌ Hard-coding what should be a tenant-tunable policy
refund_window_days = 30
```

Glossary values are declared in `manifest.contextRequirements.glossary[]`; install-time validation refuses an agent that reads a term the manifest didn't declare.

---

## 7. Handling vendor-specific attributes — the `_source` escape

The canonical response shape covers business-meaningful fields. Vendor-specific attributes (Shopify tags, Zendesk `requester.custom_fields.<id>`, NetSuite internal IDs) are available via `_source` on the normalised response — a conscious choice that costs portability for that specific field.

```python
# ✅ Read a canonical field (portable)
customer["vip_tier"]  # works across every connector that implements this capability

# ✅ Read a vendor-specific field via _source (portable to that vendor only)
#    Mark the ties-to-vendor assumption in a comment so a reviewer sees it.
# NOTE: ties this read to the shopify connector; not portable to other backends
tags = customer["_source"].get("tags", [])
```

```python
# ❌ Reading a vendor-specific field as if it were canonical
customer["tags"]  # KeyError on any connector that isn't Shopify
```

**Rule of thumb:** every `_source` read is a tiny version of the direct-SDK escape hatch (§9). Use it when you must. Flag it in a comment. If you find yourself making a lot of them, the capability's canonical shape probably needs a field added — see §9 "Missing capabilities".

---

## 8. Error handling

### 8.1 The error taxonomy

Capability calls can fail in a small number of well-named ways. Agents should branch on these rather than catching bare exceptions.

```python
from konstera_sdk import CapabilityError

# ✅
try:
    customer = await ctx.capability.call("customers.lookup_by_email", email=email)
except CapabilityError.NotFound:
    customer = None
except CapabilityError.Unbound:
    # The operator didn't bind this capability. Should be caught at install;
    # defensive branch here in case it slipped through.
    return ctx.escalate(reason="capability_unbound")
except CapabilityError.UpstreamFailure as e:
    # Vendor returned 5xx or timed out. Kernel already retried per the
    # Temporal activity policy; this exception means retries exhausted.
    return ctx.escalate(reason="upstream_down", detail=e.detail)
except CapabilityError.ResponseShapeInvalid as e:
    # The connector returned data that doesn't match the canonical shape.
    # This is a connector bug, not an agent bug — surface it.
    ctx.log.error("response shape invalid", detail=e.detail)
    return ctx.escalate(reason="shape_invalid")
```

```python
# ❌ Catching bare exceptions and treating all failures the same
try:
    customer = await ctx.capability.call("customers.lookup_by_email", email=email)
except Exception:
    customer = None  # eats upstream failures silently
```

### 8.2 The platform retry contract

The kernel wraps every capability call in a Temporal activity. Retries are automatic per the manifest's `retryPolicy` block (default: exponential backoff, 3 attempts). When your agent sees `UpstreamFailure`, retries are already exhausted — do not add your own retry loop.

```python
# ❌ Adding a retry loop around a capability call
for attempt in range(3):
    try:
        customer = await ctx.capability.call("customers.lookup_by_email", email=email)
        break
    except Exception:
        await asyncio.sleep(2 ** attempt)
```

Retries are the kernel's job. Backoff tuning belongs in the manifest, not in agent code.

### 8.3 Logging + metrics

Use the kernel's log + metric surface so observability flows through to the portal and the cost ledger.

```python
# ✅
ctx.log.info("customer resolved", customer_id=customer["id"], vip=customer["vip_tier"])
ctx.metrics.counter("refunds.approved").inc()
```

```python
# ❌
print(f"customer resolved: {customer['id']}")  # lost; not surfaced to the portal
```

---

## 9. The escape hatch — when direct APIs are still right

Capability indirection is the recommended pattern. It is not the only pattern. Direct vendor SDK calls are legitimate (and supported — see ADR-046 D2) when:

- The agent will only ever serve one business running one system, and the business owner knows portability is not a goal.
- You're building a PoC or internal scratch tool.
- A required capability isn't in the catalogue yet (see "Missing capabilities" below for the preferred alternatives).
- You genuinely need vendor-specific behaviour the canonical shape doesn't model and `_source` isn't enough.

**What you forfeit** when you take the escape hatch:
- Cost attribution via `usage_events` for that call.
- Rate limiting at the connector boundary.
- PII masking + audit log.
- Portability across connectors.
- The operator-visible binding on the portal's agent-detail page shows "observability reduced".

**How to document it** so a reviewer sees the choice:

```python
# ✅ If you must escape, mark it clearly
# ESCAPE: direct SDK call — this agent is Shopify-only by design.
# No canonical capability exists for Shopify tag batch updates (as of 2026-10).
# See docs/building-agents/capabilities-and-ontology.md §9 for the trade.
import shopify
shopify_customer = shopify.Customer.find(id=customer["id"])
shopify_customer.tags = ",".join(current_tags + ["processed"])
shopify_customer.save()
```

### Missing capabilities — three options in order of preference

1. **Open a PR against the capability catalogue.** Right long-term answer. The capability becomes shareable with every other agent that needs it. Review time: days–weeks.
2. **Use `connections.capability_overrides`.** The operator writes a per-connection recipe that implements the capability for just this connection. Works today. Not shareable across other tenants' connections of the same type.
3. **Take the escape hatch above.** Fastest. Permanently ties this one agent to this one vendor.

See `platform/docs/adr/013-agent-capabilities.md` for the technical shape of the override mechanism.

---

## 10. The ❌/✅ cheat-sheet (one-shot for a chat LLM)

Paste this into a chat LLM at the start of a Konstera-agent-build session.

```python
# ─── READS ──────────────────────────────────────────────────────────

# ✅  customer = await ctx.capability.call("customers.lookup_by_email", email=email)
# ❌  import shopify; shopify.Customer.find(email=email)

# ✅  if customer["vip_tier"] == "platinum": ...        # canonical enum
# ❌  if "tier:platinum" in customer.tags: ...          # vendor-specific tag parsing

# ✅  for candidate in [primary, *fallbacks]:            # ontology-driven order
#         value = ticket["requester"].get(candidate.field)
#         if value: customer = await ctx.capability.call(candidate.capability, value=value)
#         if customer: break
# ❌  (customer_by_email() or customer_by_phone() or customer_by_loyalty())  # hard-coded order

# ✅  if await ctx.capability.available("refunds.create"): ...     # branch on optional
# ❌  await ctx.capability.call("refunds.create", ...)             # fails if unbound

# ─── WRITES ─────────────────────────────────────────────────────────

# ✅  await ctx.capability.call("refunds.create", ..., idempotency_key="refund:tkt_1:ord_7")
# ❌  await ctx.capability.call("refunds.create", ...)             # retry can duplicate

# ✅  decision = await ctx.human.request(draft=..., policy="require-approval")
# ❌  await ctx.capability.call("tickets.reply", body=draft_body)  # bypasses reviewer

# ─── CONTEXT ────────────────────────────────────────────────────────

# ✅  entity = await ctx.context.ontology.get("customer")
# ❌  entity.key_attributes["tags"]                                 # not in ontology; vendor-specific

# ✅  window = await ctx.context.glossary.get("refund_window_days")
# ❌  refund_window = 30                                             # hard-coded; should be tenant-tunable

# ─── VENDOR-SPECIFIC ────────────────────────────────────────────────

# ✅  tags = customer["_source"].get("tags", [])        # with a comment noting the vendor tie
# ❌  tags = customer["tags"]                           # fails on non-Shopify connectors

# ─── ERRORS ─────────────────────────────────────────────────────────

# ✅  except CapabilityError.NotFound: ...               # named branches
# ❌  except Exception: ...                               # eats upstream failures silently

# ✅  (no retry loop — kernel handles retries per manifest.retryPolicy)
# ❌  for attempt in range(3): try: ... except: await asyncio.sleep(2**attempt)

# ─── OBSERVABILITY ──────────────────────────────────────────────────

# ✅  ctx.log.info("customer resolved", customer_id=customer["id"])
# ❌  print(f"customer resolved: {customer['id']}")

# ─── MANIFEST ───────────────────────────────────────────────────────

# ✅  Every capability called in code is declared in manifest.capabilities.needs[]
# ❌  Code calls ctx.capability.call("new_capability") without manifest entry
```

---

## 11. Related reading

- **[end-to-end-journey.md](end-to-end-journey.md)** — the 13-phase lifecycle this doc specialises for the code-writing phase.
- **[llm-dev-workflows.md](llm-dev-workflows.md)** — how to drive this pattern with Claude Code, Cursor, Claude Desktop, and web chat LLMs.
- **[AGENTS.md](AGENTS.md)** — the scaffold template every new agent project copies in; shorter version of §2 + §10 for in-project reading by LLM dev tools.
- **`schemas/capability-catalog.json`** — authoritative list of capabilities + canonical response schemas.
- **`schemas/agent-manifest.v3.json`** — manifest validation rules.
- **`platform/docs/adr/013-agent-capabilities.md`** — technical ADR behind the pattern.
- **`platform/docs/adr/046-capability-indirection-dx-and-lock-in.md`** — strategic framing including D2 (escape hatch) and D4 (LLM-ready docs).
- **`wiki/concepts/capability-architecture.md`** — comprehensive internal reference.
- **`wiki/concepts/ontology.md`** — Fragrance Shop refund scenario walkthrough.
