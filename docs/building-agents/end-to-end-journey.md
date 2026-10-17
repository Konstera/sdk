# Building a Konstera agent — the end-to-end journey

> **Who this is for.** Developers building Konstera agents from scratch — whether by hand, with an IDE-integrated LLM (Cursor, Claude Code, Windsurf, Zed), with a chat LLM that has tool access (Claude Desktop + Konstera DevX MCP), or with a pure chat LLM (ChatGPT web, Gemini, Claude.ai web). This doc covers all three.
>
> **Why this doc exists.** Capability indirection (see [capabilities-and-ontology.md](capabilities-and-ontology.md)) means an agent does not import vendor SDKs — it calls business verbs (`ctx.capability.call("customers.lookup_by_email", …)`) that the platform resolves to real vendor APIs at runtime. That's great for portability, but it creates a developer-experience problem: *how do you test an agent locally when it doesn't talk to any real vendor?* This document is the honest answer.
>
> **How to read it.** Skim §1 for the 13-phase map. Jump to §2 for a specific phase. Jump to §3 if you're building with an LLM (which, in 2026, is most of you).

---

## 1. The journey at a glance

Thirteen phases from idea to retirement. Each one labelled with its current state so you know what works today vs. what's planned.

| # | Phase | Status |
| - | ----- | ------ |
| 1 | **Pick + scope** — choose the agent, pick the capabilities | Today: browse the capability catalogue in `platform/schemas/`. Planned: catalogue page on konstera.ai and a `catalogue.search` MCP tool. |
| 2 | **Scaffold** — new project from a template | Today: copy a reference agent from `agents/`. Planned: `konstera init agent <name>` CLI + `scaffold.create_agent` MCP tool. |
| 3 | **Declare dependencies** — manifest `capabilities.needs[]`, `contextRequirements`, `eval.scenarios` | Today: hand-edit `manifest.json` against the published schema. Planned: interactive scaffolder; LLM-friendly validation errors. |
| 4 | **Write agent code** — orchestration against the SDK | Today: `sdk/python/` and `sdk/dotnet/` ship. [capabilities-and-ontology.md](capabilities-and-ontology.md) covers the pattern. |
| 5 | **Define fixtures** — canonical-shape sample responses | Today: hand-write `fixtures/*.json`. Planned: `fixture.generate` MCP tool; capture-from-live via `konstera record`. |
| 6 | **Run locally** — exercise the agent end-to-end | Today: `docker compose up` in platform repo + stub-mode kernel reading from `fixtures/`. Planned: wrapped as `konstera dev`. |
| 7 | **Test scenarios** — scripted inputs → expected outputs (per ADR-044) | Today: `eval_harness.py` pattern copied from reference agents. Planned: `konstera test` CLI + CI recipe. |
| 8 | **Build the OCI image** | Today: standard `docker build`. — works. |
| 9 | **Publish** | Today: push to any OCI registry. Planned: `konstera publish` wrapper. |
| 10 | **Install at tenant** | Today: portal install flow (per ADR-038 install-time contract). — works. |
| 11 | **Bind capabilities** at install time | Today: per-agent binding panel in portal. Planned: tenant-default bindings (ADR-047 candidate — parked). |
| 12 | **Monitor + iterate** | Today: portal shows invocations, cost, approvals. — works. |
| 13 | **Deprecate** | Today: portal disable + delete workflow. — works. |

The gaps that bite the hardest in agent-authoring are **phases 5, 6, and 7** — fixtures, local run, tests. Everything downstream of "write some code" currently requires either copying a reference-agent test harness or having a live tenant. §4 covers how LLM-driven dev tools reduce that friction.

---

## 2. Phase-by-phase guidance

### 2.1 Pick + scope

Before you write anything, answer three questions:

1. **What business problem does the agent solve?** (Not: what technology does it use?)
2. **What capabilities does it need to read or write?** Browse the catalogue — current entries live in `platform/schemas/capability-catalog.json`. If a capability you need doesn't exist, see §5 *Common failure modes → missing capability*.
3. **What semantic context does it depend on?** Glossary terms? Ontology entities? These go in the manifest's `contextRequirements` so install-time validation catches missing context.

The output of this phase is a one-paragraph brief and a bullet list of capability names. Not code yet.

### 2.2 Scaffold

Fastest start today: pick the reference agent closest to your use case from `agents/` and copy its layout.

- **CS-style agent (reads tickets, drafts replies, uses human-in-the-loop)** → copy `agents/customer-service-agent/`
- **Finance-style agent (reads structured records, writes approvals)** → copy `agents/prepayments-agent/`
- **Minimal starter** → copy `agents/hello-world-python/`

A scaffolded project should contain:

```
my-agent/
├── manifest.json              # dependencies: capabilities, context, scenarios
├── skill_runner.py            # agent business logic (Python example)
├── fixtures/                  # canonical-shape sample responses for local dev
│   ├── customers.lookup_by_email/
│   │   ├── jane_platinum.json
│   │   └── unknown.json
│   └── tickets.list_new/
│       └── empty.json
├── tests/
│   └── test_scenarios.py      # scenario runner using eval_harness
├── Dockerfile
├── docker-compose.dev.yml     # local kernel in stub mode + this agent
├── pyproject.toml
├── AGENTS.md                  # LLM-targeted project guide (see §4)
└── README.md
```

Only `manifest.json`, `skill_runner.py`, and `AGENTS.md` are specific to the agent being built — the rest is boilerplate.

**Planned:** `konstera init agent my-agent --template customer-service-python` will produce the above in one command. Also exposed as the `scaffold.create_agent` MCP tool for LLM dev clients.

### 2.3 Declare dependencies

The manifest is the install-time contract — portal validates it, operators read it, LLM tools generate code from it. Three required top-level blocks:

```jsonc
{
  "name": "my-cs-agent",
  "version": "0.1.0",
  "capabilities": {
    "needs": [
      { "name": "customers.lookup_by_email", "required": true },
      { "name": "tickets.reply",             "required": true },
      { "name": "orders.lookup_by_number",   "required": false }
    ]
  },
  "contextRequirements": {
    "glossary": ["refund_window_days", "vip_tier"],
    "ontology": ["customer", "order", "ticket"]
  },
  "eval": {
    "scenarios": [
      {
        "id": "platinum_refund_in_window",
        "input":    { "ticket_id": "tkt_001" },
        "expected": { "action": "refund_approved", "window_days": 60 }
      }
    ]
  }
}
```

**Rules the validator enforces:**
- Every `capabilities.needs[]` name must exist in the global catalogue.
- Every `contextRequirements.glossary[]` term must exist in the standard-context-pack or in a tenant-authored add.
- Every `eval.scenarios[]` has a well-formed input + expected block.

See the full schema at `sdk/schemas/agent-manifest.v3.json`.

### 2.4 Write agent code

The core pattern — identical in Python and .NET:

```python
# ✅ The Konstera way
customer = await ctx.capability.call(
    "customers.lookup_by_email",
    email=ticket["requester"]["email"],
)
if customer["vip_tier"] == "platinum":
    refund_window = 60

# ❌ What LLMs trained on general dev content WILL suggest — don't accept it
import shopify
customer = shopify.Customer.find(email=…)
if "tier:platinum" in customer.tags:
    refund_window = 60
```

Full ❌/✅ pattern library in [capabilities-and-ontology.md](capabilities-and-ontology.md). The agent reads canonical fields that the catalogue defined — the vendor's native field names (Shopify tags, NetSuite custinternalid, Zendesk custom fields) do not appear in agent code.

### 2.5 Define fixtures

A fixture is a JSON file containing a canonical-shape response. The local kernel's stub-connector mode reads these instead of calling real vendors. One file per `(capability, scenario)` pair.

```jsonc
// fixtures/customers.lookup_by_email/jane_platinum.json
{
  "match": { "email": "jane@example.com" },
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

The `match` block selects which fixture to return based on input. If multiple fixtures match, the kernel returns the first one. If none match, the kernel returns a 404-equivalent and the test records the fact.

**Where fixture content comes from:**
- Hand-written from the catalogue's canonical schema (`capability_catalog.response_schema`).
- Captured from a live dev tenant via `konstera record --capability customers.lookup_by_email --save-as jane_platinum` *(planned — not shipped)*.
- Generated by an LLM dev tool that calls the `fixture.generate` MCP tool with a scenario hint *(planned)*.

### 2.6 Run locally

The dev loop today:

```bash
# One-time setup: clone the Konstera platform repo as a sibling
cd ~/code/konstera/
git clone https://omnicx.visualstudio.com/Konstera/_git/Platform platform

# Start the local kernel in stub mode, pointed at your fixtures
cd platform
FIXTURES_DIR=../my-agent/fixtures docker compose -f docker-compose.dev.yml up -d

# Install your agent against the local kernel
cd ../my-agent
konstera-agent install .   # or: docker build . && docker run ...

# Trigger an invocation
curl -X POST http://localhost:4500/api/agents/my-agent/invoke \
     -d '{"ticket_id": "tkt_001"}'
```

Agent reads canonical-shape responses from your fixtures via the kernel. No vendor accounts needed. No network calls to Shopify / Zendesk / NetSuite.

**Planned:** `konstera dev` wraps all of the above into one command. The IDE-integrated LLM then just has to say `konstera dev --watch`.

### 2.7 Test scenarios

Scenarios declared in the manifest's `eval.scenarios[]` are the agent's acceptance tests. Each scenario has an input (what event triggers the agent) and an expected (what the agent should do).

Run them against the local kernel + fixtures:

```bash
konstera-agent test .     # today: python -m eval_harness ./manifest.json
```

Deterministic mode (default): all capability calls answered by fixtures. Live mode (`--live`): capability calls flow to real connectors bound in a dev tenant.

A passing test confirms three things: the agent code works, the fixtures are shaped correctly, and the scenario's assertions hold.

### 2.8–2.13

The remaining phases (build, publish, install, bind, monitor, deprecate) work today without agent-specific changes. See the platform docs for operator-side flows:
- Build: standard `docker build -f Dockerfile .`
- Publish: `docker push <registry>/<org>/<agent>:<tag>`
- Install: operator uses the portal's install flow (see `platform/docs/runbooks/agents-faq.md`)
- Monitor: portal's invocation panel, cost ledger, approvals inbox

---

## 3. Developer experience by LLM tool category

Three categories of LLM dev tool, three different workflows. The one you use dictates which Konstera surface the LLM pulls from.

### 3.1 IDE-integrated LLM (Cursor, Claude Code, Windsurf, Zed, VS Code preview)

**What the LLM can do:** read local files, run shell commands, iterate on test output. If the workspace already has your agent project cloned, the LLM reads from it directly.

**What we provide for this case:**

| Surface | Purpose |
| ------- | ------- |
| `AGENTS.md` at the project root | Dense LLM-targeted guide. Covers project layout, must-use patterns, dev commands, common pitfalls. The scaffold copies a template into every new project — see §3.1.1. |
| `CLAUDE.md` at the project root | Same content, Claude-Code-specific filename convention. Scaffold writes both as symlinks or copies. |
| `sdk/docs/building-agents/` | The LLM reads these when it needs more depth than `AGENTS.md` carries. |
| Honest error messages | `konstera test` output includes the capability name that failed, the expected vs actual shape, and a doc URL. The LLM can act on this directly in a fix-iterate loop. |

**The workflow:**

1. **Dev**: *"Build me a Konstera agent that handles refund requests for VIP customers."*
2. **LLM** reads `AGENTS.md`, the capability catalogue (from a bundled copy in the scaffold or by running `konstera-agent catalogue list` *(planned)*), and the reference agents in `agents/`.
3. **LLM** scaffolds a new project — today, by copying `agents/customer-service-agent/`; later, via `konstera init`.
4. **LLM** edits `manifest.json` to add the capabilities it chose, writes `skill_runner.py`, drops sample `fixtures/*.json` with canonical-shape data.
5. **LLM** runs `docker compose up` + `konstera-agent test .`. Reads failures, iterates. The dev watches, approves changes, commits.

**What to expect from this workflow today:** steps 1, 4, 5 work well — IDE LLMs are good at writing code given a reference. Steps 2 and 3 have friction because the catalogue is scattered and scaffolding is manual. The AGENTS.md template (next commit) closes most of step 2's gap by giving the LLM a dense project-local index of the capability pattern.

### 3.2 Chat LLM with tool / MCP access (Claude Desktop, Cursor's MCP mode, future ChatGPT with native tools)

**What the LLM can do:** call tools via MCP. May or may not have local file access.

**This is the highest-leverage category** because MCP is a bidirectional contract — we provide tools, the LLM calls them with precise arguments and gets structured responses. No hallucination of catalogue entries. No stale docs.

**What we're building for this case:**

**Konstera DevX MCP server** — a developer-facing MCP server (distinct from the agent-runtime MCP services the kernel exposes). The developer's Claude Desktop / Cursor / etc. connects to it and gets authoritative Konstera tools.

Scope for v1 (6-mini — ships in the next commit batch):

| Tool | What it returns |
| ---- | --------------- |
| `catalogue.list_capabilities(category?)` | All capability names + one-line descriptions. The LLM uses this to discover what's possible. |
| `catalogue.get_capability(name)` | Full canonical response schema, argument spec, usage example. The LLM reads this before writing a `ctx.capability.call(...)` line. |
| `catalogue.search(query)` | Semantic match on capability name + description. "Look up customer by email" → `customers.lookup_by_email`. |

Scope for v2 (planned):

| Tool | What it returns |
| ---- | --------------- |
| `scaffold.create_agent(name, template, language)` | Project directory specified by the template; the LLM then edits the generated files. |
| `fixture.generate(capability, scenario_hint)` | Canonical-shape fixture JSON matching the capability's schema. |
| `manifest.validate(path)` | Validation errors with doc URLs. |
| `scenario.suggest(agent_dir)` | Reads skill_runner.py, proposes test scenarios. |

**Installation:** `npx @konstera/devx-mcp` — zero infra, each developer runs locally against the public capability catalogue mirror. Hosted deployment is a later consideration.

**The workflow:**

1. **Dev**: *"Build me a Konstera agent that handles refund requests for VIP customers."*
2. **LLM** calls `catalogue.search("refund")` → returns `refunds.create`, `orders.lookup_by_number`, `customers.lookup_by_email`.
3. **LLM** calls `catalogue.get_capability("customers.lookup_by_email")` → returns the canonical shape (email, vip_tier, lifetime_value, …).
4. **LLM** writes the agent code with correct capability names and field access. Zero chance of hallucinating `shopify.customers.find`.
5. **LLM** (v2) calls `scaffold.create_agent(...)` to generate project files, then `fixture.generate(...)` to seed test fixtures.
6. Dev reviews and runs.

**Why this matters:** docs-reading LLMs guess at API shape; MCP-connected LLMs retrieve ground truth. For a platform that generates most of its agent code via LLMs, the correctness delta compounds across every agent built.

### 3.3 Pure chat LLM (ChatGPT web, Gemini web, Claude.ai web — no MCP, no filesystem)

**What the LLM can do:** read documents it has access to (training data + browsing). Return text that the dev copy-pastes into their editor.

**This is the hardest case** because the LLM is operating blind to the dev's project. We can't give it tools; we can only make sure the public docs it finds are correct and dense.

**What we provide for this case:**

| Surface | Purpose |
| ------- | ------- |
| `https://konstera.ai/sdk/llms.txt` | Index page listing SDK doc URLs, convention standardised at <https://llmstxt.org>. LLMs with web browsing find this first. |
| `https://konstera.ai/sdk/llms-full.txt` | Single dense file containing the full SDK reference — capability catalogue, canonical shapes, pattern library, dev-loop commands. Target <50 KB so the LLM can swallow it in one load. |
| `/resources/ontology-and-the-cost-of-change` | The marketing article (public) that explains the pattern. Not a reference but hits the top of search results and primes the LLM with the correct framing. |
| ❌/✅ pattern pairs throughout the docs | LLMs pattern-match aggressively on these; a few dozen pairs materially change what the LLM generates. |

**The workflow:**

1. **Dev**: *"Write me a Konstera agent in Python that looks up a customer by email and extends the refund window if they're platinum."*
2. **LLM** either has training-time knowledge of Konstera (if it's recent and we've been found) or browses to `konstera.ai`. Finds `llms.txt`, fetches `llms-full.txt`.
3. **LLM** writes the code based on what it found — correct if `llms-full.txt` is current, hallucinated if it's stale.
4. Dev copy-pastes into their local project, runs, iterates manually by feeding errors back to the chat.

**Honest about this workflow's limits:** it won't be as reliable as §3.1 or §3.2 because the feedback loop crosses a browser clipboard. The best we can do is make sure the public docs the LLM finds are correct, dense, and well-ranked.

---

## 4. Common failure modes and how to recover

### 4.1 Hallucinated capability name

**Symptom:** agent install fails with *"capability `customers.find_by_email` not in catalogue."* (LLM invented a plausible name.)

**Recovery:**
- IDE LLM (§3.1): paste the error into the chat; the LLM reads it and tries another name. Usually resolves in one iteration.
- MCP LLM (§3.2): LLM shouldn't hit this because `catalogue.list_capabilities` returned the real names.
- Pure chat (§3.3): ask the LLM to list its assumed capability names; cross-check against `llms-full.txt`.

### 4.2 Fixture shape mismatch

**Symptom:** `konstera-agent test` reports *"fixture missing required field `vip_tier`"*.

**Recovery:** the fixture doesn't match the capability's canonical shape. Fix: load the capability spec (`catalogue.get_capability` or the schema file) and align the fixture. The error message includes the required fields.

### 4.3 Missing capability

**Symptom:** the agent needs a verb that doesn't exist in the catalogue (e.g. *"products.lookup_by_barcode"* — hypothetical).

**Three options**, in order of preference:
1. **Add the capability to the catalogue** — open a PR against the capability catalogue repo. Right long-term answer. Slower.
2. **Use `connections.capability_overrides`** — operator writes a per-connection recipe. Works today. Not shareable across other agents.
3. **Use the direct-SDK escape hatch** — import the vendor SDK, lose portability for this one capability. See [capabilities-and-ontology.md §4](capabilities-and-ontology.md#4-when-direct-api-calls-are-still-right).

### 4.4 Local kernel won't start

**Symptom:** `docker compose up` fails with port conflicts.

**Recovery:** Konstera reserves ports 4500–4512. If something else is bound to one of these, change it or stop the other process. The platform README has the full port map.

### 4.5 LLM wrote code against the capability pattern but imported a vendor SDK too

**Symptom:** agent code has both `ctx.capability.call(...)` and `import shopify` — the LLM hedged.

**Recovery:** this is usually a prompting issue. Tell the LLM explicitly: *"use only the capability pattern, no vendor SDKs."* The AGENTS.md template in your project should already set this constraint; if the LLM ignored it, make it louder.

### 4.6 Install succeeds but the agent fails at runtime with "capability unbound"

**Symptom:** the manifest declared a capability as required; the operator didn't bind it before enabling the agent.

**Recovery:** this should be caught at install time — the portal's install flow enforces required bindings. If it slipped through, the operator binds it in the agent's capability-bindings panel. See `platform/docs/runbooks/agents-faq.md`.

---

## 5. What's shipping when (honest)

This is a snapshot — check the SDK roadmap for current.

**Shipped**
- SDK packages (`sdk/python`, `sdk/dotnet`) — stable, PyPI/NuGet pending publication
- Manifest schema v3 — stable
- Reference agents (`agents/*`) — stable, pattern reference
- Platform kernel with stub-mode connectors — works via docker compose

**Next commit batch (same work stream as this doc)**
- `AGENTS.md` + `CLAUDE.md` template for scaffolded projects
- `sdk/docs/building-agents/capabilities-and-ontology.md` — SDK developer guide with ❌/✅ pairs
- `sdk/docs/llms.txt` + `sdk/docs/llms-full.txt`
- Konstera DevX MCP server at 6-mini scope (`catalogue.*` tools) — `npx @konstera/devx-mcp`
- Documented fixture file format + a `docker-compose.dev.yml` recipe

**Planned (separate work streams)**
- `konstera init`, `konstera dev`, `konstera test`, `konstera record` CLIs
- DevX MCP server v2 (`scaffold.*`, `fixture.*`, `manifest.*`, `scenario.*` tools)
- Browsable capability catalogue page on konstera.ai
- Tenant-default capability bindings (ADR-047 candidate)

---

## 6. Related reading

- **[capabilities-and-ontology.md](capabilities-and-ontology.md)** — the pattern itself, with ❌/✅ pairs. Read this before writing any agent code.
- **[konstera.ai/resources/ontology-and-the-cost-of-change](https://konstera.ai/resources/ontology-and-the-cost-of-change)** — the business framing of capability indirection.
- **platform/docs/adr/013-agent-capabilities.md** — the technical ADR this all rests on.
- **platform/docs/adr/046-capability-indirection-dx-and-lock-in.md** — the strategic framing of the trade.
- **wiki/concepts/capability-architecture.md** — the comprehensive internal reference.
- **wiki/concepts/ontology.md** — the Fragrance Shop refund scenario walkthrough.
