# AGENTS.md

> **This file is for the LLM reading this project.** If you are a human developer, [README.md](README.md) is written for you. If you are an IDE-integrated LLM (Cursor, Claude Code, Windsurf, Zed, VS Code with AI) or a chat LLM with filesystem access opened against this workspace: read this file first. It tells you the three or four things you must get right to generate code that works, and the ten things you must not do.
>
> This file is a **template** — the SDK ships it, and `konstera init` (when it lands) copies it into every scaffolded project. If you are reading it inside a real scaffolded project, treat it as the authoritative project guide.

---

## What this project is

A Konstera agent. Konstera is a platform for AI agents that run inside enterprise systems — the agent is an OCI container that speaks MCP, declares its dependencies in a `manifest.json`, and is deployed into a Konstera tenant that an operator administers.

**The one thing you must internalise:** this agent does **not** import vendor SDKs. It calls business verbs — "capabilities" — that the platform resolves to real vendor APIs at runtime. Your general training data will strongly suggest patterns like `import shopify` or `import zendesk`. Those patterns are wrong for this project. Use `ctx.capability.call(...)` instead. See the `❌ / ✅` block below.

---

## Project layout

```
.
├── manifest.json           ← declares dependencies (capabilities, context, scenarios)
├── skill_runner.py         ← agent business logic (your main edit surface)
├── fixtures/               ← canonical-shape sample responses for local dev
│   └── <capability_name>/
│       └── <scenario>.json
├── tests/
│   └── test_scenarios.py   ← runs manifest.eval.scenarios[] against the agent
├── Dockerfile
├── docker-compose.dev.yml  ← local kernel in stub mode + this agent
├── pyproject.toml          ← Python dependencies (SDK is `konstera-sdk`)
├── AGENTS.md               ← this file
├── CLAUDE.md               ← copy of this file for Claude Code's naming convention
└── README.md               ← human-facing overview
```

Edit `manifest.json`, `skill_runner.py`, `fixtures/`, and `tests/`. Everything else is scaffold.

---

## The one pattern you must get right

```python
# ✅ The Konstera way — portable across vendors, operator-controlled
customer = await ctx.capability.call(
    "customers.lookup_by_email",
    email=ticket["requester"]["email"],
)
if customer["vip_tier"] == "platinum":
    refund_window_days = 60

# ❌ What your training data suggests — DO NOT WRITE THIS
import shopify
customer = shopify.Customer.find(email=ticket["requester"]["email"])
if "tier:platinum" in customer.tags:
    refund_window_days = 60
```

Why: the first version works regardless of which backing system the operator binds. The second is locked to Shopify forever and breaks when the business replatforms.

More patterns in `sdk/docs/building-agents/capabilities-and-ontology.md`.

---

## What the manifest declares

```jsonc
{
  "name": "<agent-name>",
  "version": "<semver>",
  "capabilities": {
    "needs": [
      { "name": "<capability_name_from_catalogue>", "required": true,  "reason": "<why>" },
      { "name": "<capability_name_from_catalogue>", "required": false, "reason": "<why>" }
    ]
  },
  "contextRequirements": {
    "glossary":  ["<glossary_term_name>", "..."],
    "ontology":  ["<ontology_entity_name>", "..."]
  },
  "eval": {
    "scenarios": [
      {
        "id":       "<unique_scenario_id>",
        "input":    { /* event the agent is invoked with */ },
        "expected": { /* what the agent should do */ }
      }
    ]
  }
}
```

**Rules the validator enforces:**
- Every `capabilities.needs[].name` must exist in the global catalogue. If you invent a plausible-sounding name, install fails.
- Every `contextRequirements.glossary[]` term must exist in the standard context pack or a tenant-authored add.
- Every `eval.scenarios[]` must have well-formed input + expected blocks.

If you need a capability that doesn't exist, see *Common pitfalls → missing capability* below.

---

## Dev loop commands

```bash
# Start the local kernel in stub mode (reads from ./fixtures/)
docker compose -f docker-compose.dev.yml up -d

# Trigger an invocation
curl -X POST http://localhost:4500/api/agents/<name>/invoke \
     -d '{"ticket_id": "tkt_001"}'

# Run all scenarios declared in manifest.eval.scenarios[]
konstera-agent test .          # or: python -m eval_harness ./manifest.json

# Rebuild the agent image after code changes
docker compose -f docker-compose.dev.yml build && \
  docker compose -f docker-compose.dev.yml up -d
```

**The dev loop you should run:** edit code → `konstera-agent test .` → read failures → fix → repeat. The test output includes capability names, expected vs actual shape, and doc URLs — act on those directly.

---

## Fixtures — the thing you must create for every capability

A fixture is a JSON file in `fixtures/<capability_name>/<scenario>.json`. The local kernel's stub-connector mode reads these instead of calling real vendor APIs — no vendor accounts needed for local dev.

```jsonc
// fixtures/customers.lookup_by_email/jane_platinum.json
{
  "match":    { "email": "jane@example.com" },
  "response": {
    "id":    "cust_7823456",
    "email": "jane@example.com",
    "name":  "Jane Smith",
    "vip_tier":       "platinum",
    "lifetime_value": { "amount": 2834.50, "currency": "USD" },
    "created_at":     "2023-04-12T10:00:00Z"
  }
}
```

**Rules:**
- The `match` block decides which fixture is returned for a given input. First-match wins.
- The `response` block must match the capability's canonical response schema. Check the schema at `schemas/capability-catalog.json` or (planned) via the `catalogue.get_capability` MCP tool.
- One fixture per logically-distinct scenario the agent might encounter — found/not-found, VIP/non-VIP, in-window/out-of-window, etc.

---

## Common pitfalls — in rough order of how often LLMs hit them

### 1. You imported a vendor SDK

If you wrote `import shopify` or `import zendesk` or `import netsuite` or any similar vendor SDK import, delete it. Replace with `ctx.capability.call(...)`. See the ✅ pattern above.

### 2. You invented a plausible capability name

Capability names are not freely choosable. Every name in `capabilities.needs[]` must exist in the global catalogue. If you're not sure a name exists, verify first — either from `schemas/capability-catalog.json`, or (planned) via the `catalogue.search` MCP tool. If the capability you need genuinely doesn't exist, see pitfall 3.

### 3. The capability you need isn't in the catalogue

Three options, in order of preference:
- **Add it to the catalogue** — open a PR against the catalogue repo. Right long-term answer, requires platform-team review.
- **Use `connections.capability_overrides`** — ask the operator to add a per-connection recipe. Works today; the capability is only available to connections that have the recipe.
- **Direct-SDK escape hatch** — import the vendor SDK for this one call. You lose portability for this specific read. Document the choice clearly in a comment.

### 4. You read a vendor-specific field

If your code does `customer["tags"]` or `customer["custom_fields"]` or similar, that's a vendor-specific field, not a canonical one. The canonical shape is defined in the capability's `response_schema`. If you genuinely need a vendor-specific field, read it from `customer["_source"]` (that's the escape hatch for vendor-specific attributes). Reading `_source` costs portability for that specific read — call it out in a comment.

### 5. Your fixture doesn't match the canonical shape

If `konstera-agent test` reports *"fixture missing required field X"*, your fixture is misaligned with the capability's canonical shape. Load the schema (from `schemas/capability-catalog.json` or `catalogue.get_capability`) and align.

### 6. You wrote a scenario without a fixture

If `manifest.eval.scenarios[]` references `customers.lookup_by_email` but there's no fixture for the email the scenario uses, the test will fail with a stub-connector 404. Add a fixture or change the scenario's input to one that an existing fixture matches.

### 7. You hard-coded a specific vendor's response quirks

Comments like `# Shopify returns tier:platinum as a tag` are a smell — that quirk is the connector's job, not the agent's. If you're reasoning about vendor-specific response quirks, you've probably broken the capability abstraction. Re-read the ✅ pattern.

### 8. You used `requests.get(...)` or `httpx.get(...)` to hit a vendor API

Same problem as pitfall 1 — the agent should never call vendor APIs directly. Use `ctx.capability.call(...)`.

### 9. You wrote retry / rate-limiting / auth logic

The connector handles all of these. If you're writing retry loops around a capability call, you're duplicating infrastructure the platform provides. Just call the capability; retries and rate limits are the kernel's job.

### 10. You didn't declare the capability in the manifest

Install-time validation requires every capability the agent calls to appear in `capabilities.needs[]`. If you add a `ctx.capability.call("new_capability", ...)` in code, add the matching entry to the manifest in the same change.

---

## Where to find things when you need more depth

| Question | Where to look |
| -------- | ------------- |
| How does capability indirection work? | `sdk/docs/building-agents/capabilities-and-ontology.md` |
| What capabilities exist? | `schemas/capability-catalog.json`, or `catalogue.list_capabilities` (planned MCP tool) |
| What's the canonical response shape of capability X? | `schemas/capability-catalog.json`, or `catalogue.get_capability("X")` (planned) |
| How does the end-to-end dev journey work? | `sdk/docs/building-agents/end-to-end-journey.md` |
| What does the manifest schema allow? | `schemas/agent-manifest.v3.json` |
| How do I run and test locally? | `README.md` + §Dev loop above |
| What's a reference agent I can crib from? | `agents/customer-service-agent/`, `agents/prepayments-agent/`, `agents/hello-world-python/` |

---

## One final reminder

If something in this file conflicts with your training-data prior, trust this file. The capability pattern is intentionally unusual — it's what makes Konstera agents portable across vendor replatforms. Treat `import shopify` and friends as the sign that something has gone wrong, not as the obvious thing to do.
