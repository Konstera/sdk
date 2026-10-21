# Building Konstera agents with Claude Code (and other LLM dev tools)

> **Who this is for.** You're a developer who will build Konstera agents with help from an LLM — Claude Code, Cursor, Windsurf, Zed, Claude Desktop, ChatGPT, or Gemini. This doc answers every question that came up during the capability-indirection design review: how the Konstera CLI composes with Claude Code's CLI, how a Konstera DevX MCP server fits into Claude Desktop, how to drive the whole dev loop end-to-end, and what to do when any of them hallucinates something.
>
> **Related.** The pattern this document assumes is capability indirection: Konstera agents call business verbs (`ctx.capability.call("customers.lookup_by_email", …)`), not vendor SDKs. If that's new, read [capabilities-and-ontology.md](capabilities-and-ontology.md) first; the full end-to-end lifecycle is in [end-to-end-journey.md](end-to-end-journey.md). This doc is the LLM-tool-specific angle on the same journey.

---

## 1. The questions this document answers

Numbered so you can skim to the one you have:

1. [Why does any of this need its own doc?](#2-why-llm-driven-agent-dev-needs-its-own-answer) The agent pattern breaks the "just hit the vendor sandbox" dev loop.
2. [What tools compose during a Konstera agent build?](#3-the-cli-layers) Konstera CLI, Claude Code CLI (or Cursor, etc.), MCP, and standard dev tools.
3. [How does the Konstera CLI fit with Claude Code specifically?](#4-pattern-a-claude-code-cli-drives-konstera-cli) Same way `git` or `docker` fit — Claude Code runs it via its Bash tool.
4. [What's the role of the Konstera DevX MCP server?](#5-pattern-b-chat-llm-with-konstera-devx-mcp) Authoritative catalogue + scaffolding tools that any MCP-speaking LLM can call directly.
5. [Which LLM tools work best for agent dev, and why?](#8-tool-by-tool-setup) IDE-integrated with filesystem + CLI; chat LLMs with MCP; pure chat (least reliable).
6. [How do I actually scaffold, edit, test, and iterate?](#7-four-concrete-workflows) Four concrete workflows with commands.
7. [What do I do when the LLM hallucinates or writes the wrong pattern?](#9-faq) Covered under FAQ and the pitfalls section of `AGENTS.md`.
8. [Where does Claude Code's skills / hooks / slash-commands system fit?](#4-pattern-a-claude-code-cli-drives-konstera-cli) Via a shipped Konstera agent-dev skill (planned); until then, project `AGENTS.md` carries the context.
9. [How is this different for Cursor / Windsurf / Zed users?](#8-tool-by-tool-setup) Same shape; different filenames and tool-call conventions.
10. [What's shipping now vs. planned?](#10-whats-shipping-now-vs-planned) Honest table at the end.

---

## 2. Why LLM-driven agent dev needs its own answer

Standard agent development has a built-in dev loop:

```
1. import <vendor-sdk>
2. point at vendor sandbox / dev store
3. run code, observe behaviour against real-shaped responses
4. iterate
```

Capability indirection breaks step 1 by design (vendor dependency moves out of the agent) and therefore breaks step 2 (there's no vendor sandbox to hit). Something has to fill the gap:

- **For humans**: a local kernel in stub mode reading fixture files (phase 6 in the journey doc).
- **For LLMs**: the same local kernel, plus a way for the LLM to discover what capabilities exist, what shapes they return, and how to generate correct code against the pattern without defaulting to its training-data prior of `import shopify`.

In 2026 the second case is the dominant one — most Konstera agents will be written with LLM assistance. So the LLM-driven dev loop is a first-class product surface, not a nice-to-have.

---

## 3. The CLI layers

Four distinct CLIs end up in the same shell during Konstera agent dev. Each owns a different concern:

| CLI                          | Scope                                                                                                   | Who runs it                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **`konstera-agent` (planned)** | Agent-authoring workflow: scaffold, dev kernel in stub mode, test scenarios, record fixtures, publish  | You — directly, or Claude Code via Bash              |
| **`claude` (Claude Code CLI)** | LLM dev assistant: read files, write code, run commands, iterate on test output                        | You — in the terminal, usually `claude` or `claude -p` |
| **Chat / IDE assistant**      | Same role as Claude Code but inside another tool (Cursor's agent, Windsurf, Zed AI, VS Code with AI)   | Depends on the tool                                  |
| **Standard dev tools**        | `docker` (local kernel + agent build), `git` (version control), `npm`/`pip`/`dotnet` (SDK installs)   | Everyone                                             |

**Key composition rule:** the LLM dev assistant drives the Konstera CLI, not the other way round. If you've seen Claude Code call `git status`, `gh pr create`, or `npm test` — it will call `konstera-agent` the same way. There is no new paradigm; `konstera-agent` is a well-behaved CLI that LLM dev tools orchestrate.

The reverse direction — `konstera-agent` calling an LLM — is **not** a thing. Konstera's agent runtime calls LLMs (via `ctx.llm.chat(...)`), but that's inside a running agent at execution time, not during authoring.

---

## 4. Pattern A — Claude Code CLI drives Konstera CLI

**Setup:**
1. Install Claude Code (see Anthropic docs for the current install command).
2. Install the Konstera agent-dev tooling. Today this means cloning the SDK repo and reading the reference agents. Once the CLI ships, it will be `npm install -g @konstera/agent-cli` or equivalent per language.
3. In the directory where you want your new agent, run `claude`. Claude Code opens, reads `AGENTS.md` and `CLAUDE.md` if present, and is now your pair.

**What Claude Code reads at startup:**
- `CLAUDE.md` at the project root (its own convention) — Konstera's scaffold writes this.
- `AGENTS.md` at the project root (the broader convention) — Konstera's scaffold writes this too, as the same content.
- Imported memory files (`@~/.claude/...`) — your personal rules, if you have any.
- The repo file tree — Claude Code walks it as the conversation requires.

**What Claude Code runs via its Bash tool during a typical agent build:**

| Step | Command Claude Code runs | Why |
| ---- | ------------------------ | --- |
| Scaffold | `konstera-agent init <name> --template <template>` (planned) OR `cp -r ../agents/customer-service-agent ./my-agent` (today) | Lay down the project skeleton |
| Install deps | `pip install -e .` / `dotnet restore` | Pull in the Konstera SDK |
| Start local kernel | `docker compose -f docker-compose.dev.yml up -d` | Spin up the stub-mode kernel reading fixtures |
| Run scenarios | `konstera-agent test .` (planned) OR `python -m eval_harness ./manifest.json` (today) | Validate against the scenarios declared in the manifest |
| Watch logs | `docker compose logs -f api` | Trace what the kernel is doing |
| Rebuild image | `docker compose build` | After a code change |

**The dev loop under Claude Code:**

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. You: "Add a scenario where a non-VIP customer requests       │
│    a refund outside the window — expected: deny with reason."   │
├─────────────────────────────────────────────────────────────────┤
│ 2. Claude Code reads skill_runner.py + manifest.json + fixtures │
├─────────────────────────────────────────────────────────────────┤
│ 3. Claude Code adds a scenario to manifest.eval.scenarios[]     │
├─────────────────────────────────────────────────────────────────┤
│ 4. Claude Code creates fixtures/customers.lookup_by_email/      │
│    bob_silver.json with canonical-shape data                    │
├─────────────────────────────────────────────────────────────────┤
│ 5. Claude Code runs `konstera-agent test .`                     │
├─────────────────────────────────────────────────────────────────┤
│ 6. Test fails — "agent returned refund_approved, expected deny" │
├─────────────────────────────────────────────────────────────────┤
│ 7. Claude Code reads skill_runner.py, patches the branch logic  │
├─────────────────────────────────────────────────────────────────┤
│ 8. Claude Code re-runs `konstera-agent test .` — passes         │
├─────────────────────────────────────────────────────────────────┤
│ 9. Claude Code: "Added scenario, patched skill_runner.py line   │
│    42, test now passes. Diff is 23 lines; want me to commit?"   │
└─────────────────────────────────────────────────────────────────┘
```

This is exactly the pattern Claude Code uses for any software-engineering task — the only Konstera-specific additions are (a) `AGENTS.md` telling the LLM what the capability pattern is, and (b) the `konstera-agent` CLI commands it runs.

**Claude Code skills (planned):** Konstera will ship a skill — likely `konstera-agent-dev` — installable via `claude skills install konstera/konstera-agent-dev`. The skill bundles step-by-step instructions, patterns, and references to the AGENTS.md template. If a user invokes `/konstera-agent-dev` in Claude Code, the skill loads a focused context without having to re-read a long doc every session. Until the skill ships, project `AGENTS.md` carries the same content.

---

## 5. Pattern B — chat LLM with Konstera DevX MCP

**Setup:**
1. In your Claude Desktop (or Cursor's MCP mode, or any MCP-speaking client) config, add the Konstera DevX MCP server. When published, this will be `npx @konstera/devx-mcp` — zero local setup, each developer runs it on demand.
2. Open the chat. The LLM now has Konstera tools in its tool list without you having to say anything.

**What tools the LLM has (v1 / 6-mini scope):**

| Tool                                     | What the LLM uses it for                                                                           |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `catalogue.list_capabilities(category?)` | Discovery: *"what capabilities exist for customers / orders / tickets?"*                           |
| `catalogue.get_capability(name)`         | Reads the canonical response schema + argument spec + examples before writing a `ctx.capability.call(...)` line |
| `catalogue.search(query)`                | Semantic search: *"look up a customer by email"* → `customers.lookup_by_email`                     |

**What this changes:** docs-reading LLMs guess at API shape; MCP-connected LLMs retrieve it. The LLM calls `catalogue.get_capability("customers.lookup_by_email")`, gets back the authoritative schema, and writes code that compiles correctly on the first try. No hallucinated capability names. No invented field access. This is the single highest-leverage DX improvement Konstera can ship for the LLM-driven cohort.

**Planned v2 tools** — `scaffold.create_agent`, `fixture.generate`, `manifest.validate`, `scenario.suggest`. Once these land, the LLM can go from "describe the agent you want" to "runnable project with passing scenarios" in a handful of tool calls, with the dev reviewing the output rather than hand-driving every command.

**When Pattern B beats Pattern A:** when the dev isn't in a terminal — e.g. designing an agent on a tablet via Claude Desktop, or ideating during a design review. Claude Desktop + Konstera DevX MCP produces runnable code the dev then takes to a Pattern-A workflow for actual commits.

**When Pattern A beats Pattern B:** when the dev needs to actually run commands (tests, builds, local kernel). Claude Code's filesystem + Bash tools make that part faster.

**In practice most devs will use both:** Pattern A for the daily edit-test loop, Pattern B for exploration and when the LLM needs authoritative catalogue data.

---

## 6. Pattern C — pure chat LLM, no tools

**Setup:** none. The developer opens Claude.ai, ChatGPT, or Gemini in a browser and prompts.

**What the LLM can do:** read documents it can access (training data + browsing results). Return text the dev copy-pastes into their editor.

**What we provide for this case:**

| Surface                                          | Role                                                                                                                       |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `https://konstera.ai/sdk/llms.txt` (planned)     | Convention per <https://llmstxt.org>. One-page index of SDK doc URLs; browsing LLMs find this first.                       |
| `https://konstera.ai/sdk/llms-full.txt` (planned) | Dense single-file reference — capability catalogue, canonical shapes, pattern library, dev-loop commands. Target <50 KB.   |
| `/resources/ontology-and-the-cost-of-change`     | Public article that frames the pattern. Primes the LLM with correct framing when it finds this via general search.         |
| `AGENTS.md` published in the SDK repo            | Even without tools, the LLM can be pointed at the AGENTS.md template content as a one-shot context prime.                  |

**The workflow:** the dev describes the agent they want. The LLM returns code and a dev-loop recipe. The dev pastes into their project, runs locally, feeds any errors back as follow-up messages.

**Honest about this workflow's limits:** the feedback loop crosses a clipboard, so errors take longer to resolve than in Pattern A. The best we can do is make sure the doc the LLM lands on is dense enough that first-draft code works.

---

## 7. Four concrete workflows

Each workflow shown in the Pattern-A register (Claude Code CLI driving Konstera CLI) because that's the clearest; the Pattern-B/C equivalents are the obvious adaptations.

### 7.1 Scaffold a new agent

**You say:** *"Scaffold a Konstera CS agent that handles refund requests for VIP customers. Python."*

**Claude Code does:**

```bash
# Today — hand-pick a template
cp -r ~/code/konstera/agents/customer-service-agent ./refund-agent
cd refund-agent
# Edit manifest.json: new name, trimmed-down capabilities.needs[],
# refund-specific eval.scenarios[]
# Edit skill_runner.py: strip the sample logic, keep the ctx. patterns

# Planned once the CLI ships
konstera-agent init refund-agent --template customer-service-python
cd refund-agent
```

**Claude Code then reads** the generated `AGENTS.md` and reports what capabilities the new scaffold declared, which fixture files it created, and what the first test run looks like.

### 7.2 The edit → test → fix loop

Already shown in §4. The important observation: Claude Code reads test output and acts on it. Konstera's test harness contributes to this by producing errors the LLM can parse — capability name, expected vs actual shape, doc URL.

### 7.3 Capture fixtures from a dev tenant

Scenario: you have a dev tenant with a real sandbox Shopify connected. You want to capture real response shapes as fixtures for offline dev.

**Today:** manual. Point the agent at the dev tenant, run an invocation, read the kernel logs, hand-copy the response shape into `fixtures/`.

**Planned:**

```bash
konstera-agent record \
    --tenant dev \
    --capability customers.lookup_by_email \
    --input '{"email":"jane@example.com"}' \
    --save-as fixtures/customers.lookup_by_email/jane_platinum.json
```

Claude Code runs this when you say *"capture a fixture for Jane's platinum lookup from the dev tenant."* Captured fixtures are sanitised by default (PII masking rules in the config) and committed to the repo.

### 7.4 Debug a failing scenario

**You say:** *"The scenario `platinum_refund_in_window` is failing with 'expected refund_approved, got escalate_to_human'. Fix it."*

**Claude Code's debug steps:**

```bash
# Re-run with verbose output
konstera-agent test . --scenario platinum_refund_in_window --verbose
# Read the kernel log for this invocation
docker compose logs api --since 5m | grep -i "capability\|refund"
# Open skill_runner.py and manifest.json; cross-reference the fixture
# Diagnose, patch, re-run
```

**The thing that makes this fast:** `AGENTS.md`'s pitfall list — Claude Code sees the symptom and matches to one of the ten documented failure patterns. If it's new, Claude Code reasons from first principles against the pattern described in `capabilities-and-ontology.md`.

---

## 8. Tool-by-tool setup

### 8.1 Claude Code (`claude` CLI)

- Reads `CLAUDE.md` at project root. Konstera's scaffold writes this (same content as `AGENTS.md`).
- No MCP required for Pattern A; add Konstera DevX MCP to `claude mcp` config if you want the catalogue tools too.
- Install the planned Konstera agent-dev skill: `claude skills install konstera/konstera-agent-dev` *(planned)*. Until shipped, the AGENTS.md content fills the gap.

### 8.2 Cursor

- Reads `.cursorrules` at project root. Konstera's scaffold writes this *(planned)*, mirroring the AGENTS.md content.
- MCP support available in Cursor's agent mode — add the Konstera DevX MCP the same way as Claude Desktop.
- Cursor's inline suggestions pattern-match on nearby code, so having a well-structured reference agent in the same workspace helps generation.

### 8.3 Windsurf

- Reads project context from `AGENTS.md` (common convention adopted by Windsurf and others).
- Shell access + file edit, same shape as Claude Code.

### 8.4 Zed with AI

- Reads project context and runs tools; details depend on which model backend is wired. Treat as Pattern A.

### 8.5 Claude Desktop (chat + MCP)

- Pure Pattern B. Add `npx @konstera/devx-mcp` *(planned)* to your Claude Desktop MCP config.
- No filesystem access by default. Returns code; you paste.
- Can be upgraded to Pattern A by combining with Claude Code — Claude Desktop designs, Claude Code implements.

### 8.6 ChatGPT / Gemini / Claude.ai (web, no tools)

- Pure Pattern C. Relies on browsing to find `llms.txt` + `llms-full.txt` *(planned)*.
- Advise devs to paste the AGENTS.md content at the start of a chat session to prime the LLM with correct patterns.

### 8.7 Setup that works across all tools

Regardless of which LLM dev tool you use:

1. Have the Konstera SDK installed (or the SDK repo cloned as a sibling).
2. Have Docker running (for the local kernel).
3. Have `AGENTS.md` in your project root — if nothing else, this is the one file every LLM dev tool will read on contact.
4. (Optional) Have the Konstera DevX MCP server configured in whatever MCP-speaking tool you use.

---

## 9. FAQ

### Does the Konstera CLI replace Claude Code?

No — opposite. Konstera CLI is the toolbox; Claude Code is the hand picking tools out of it. Claude Code *runs* `konstera-agent` commands the same way it runs `git` or `docker`. Devs who prefer typing commands themselves use `konstera-agent` directly; devs who prefer the LLM-driven loop use Claude Code (or Cursor, or Windsurf) to orchestrate it.

### Does Claude Code need the Konstera DevX MCP?

No, but it's additive. Claude Code with just `konstera-agent` CLI + `AGENTS.md` is a complete workflow (Pattern A). Adding the MCP server gives Claude Code one more tool category — authoritative catalogue lookups — which eliminates the small residual hallucination risk around capability names and shapes.

### What if my LLM tool only supports MCP, not CLI access?

Use Pattern B. The DevX MCP server (planned) covers the common agent-authoring tool surface. Workflows that strictly need shell execution (actually running tests, bringing the local kernel up) have to drop to a Pattern A tool when it's time to execute — Claude Desktop designs the agent, you (or Claude Code) run it.

### How do I keep Claude Code from writing `import shopify` anyway?

Four defences, in increasing strength:
1. `AGENTS.md` at the root tells Claude Code the capability pattern is the rule and vendor imports are forbidden. This alone catches most cases.
2. ❌/✅ pairs in `AGENTS.md` + the SDK docs give pattern-matching priors something to grip.
3. Konstera DevX MCP returns authoritative catalogue entries so the LLM has nothing to invent.
4. The install-time validator refuses manifests with unknown capability names and the test harness refuses responses with mismatched shapes — if a vendor-import pattern slips through earlier defences, these catch it before it reaches a tenant.

### Will Konstera CLI commands change over time?

Yes — the CLI is pre-1.0. Breaking changes between minor versions are possible. Pin the version in your scaffold's `pyproject.toml` / `package.json` so a `konstera-agent` upgrade doesn't surprise an open LLM session. The published llms-full.txt will track the latest stable command surface.

### Does any of this require a Konstera account?

For local dev — no. The local kernel in stub mode runs entirely from fixtures. For installing an agent at a tenant and running it against real connectors — yes. For capturing fixtures from a real backend via `konstera-agent record` — yes.

### Can the Konstera DevX MCP connect to my production tenant?

Not in v1. The DevX MCP is dev-side only; it serves authoritative catalogue data (which is public) and local scaffolding. For tenant-side operations (install, bind, invoke, monitor), use the portal or (future) a separate `konstera-tenant` CLI with proper auth.

### What if a capability I need doesn't exist?

Three options, in order of preference: (1) PR against the capability catalogue repo (right long-term); (2) `connections.capability_overrides` recipe (works today, per-connection); (3) direct-SDK escape hatch (ADR-046 D2, loses portability for this call). Full detail in [capabilities-and-ontology.md](capabilities-and-ontology.md) and [end-to-end-journey.md §4.3](end-to-end-journey.md#43-missing-capability).

### How does Claude Code's slash-commands system factor in?

Once the Konstera agent-dev skill ships, `/konstera-agent-dev` loads a focused context into the session — scaffolding commands, pattern reminders, pitfall checklist. Until then, write your own tiny slash command in `~/.claude/commands/` that reads the project's `AGENTS.md`. Takes five minutes.

### Will there be a Konstera MCP server for the agent *runtime* too?

The Konstera kernel already is an MCP server — it's what agents call for `ctx.capability.call(...)`, `ctx.context.ontology.get(...)`, `ctx.llm.chat(...)`, etc. That's a different MCP than the DevX one. The runtime MCP serves agents at execution; the DevX MCP serves human and LLM developers at authoring time. Different audiences, different tool surfaces.

---

## 10. What's shipping now vs. planned

| Item                                                       | Status                                                                                   |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `sdk/python` + `sdk/dotnet` packages                       | Shipped                                                                                  |
| Manifest schema v3                                         | Shipped                                                                                  |
| Reference agents (`agents/*`)                              | Shipped                                                                                  |
| Platform kernel + local docker-compose                    | Shipped                                                                                  |
| `AGENTS.md` template                                       | Shipped (this commit batch — in `sdk/docs/building-agents/AGENTS.md`)                    |
| `end-to-end-journey.md`                                    | Shipped (this commit batch)                                                              |
| `llm-dev-workflows.md` (this doc)                          | Shipped (this commit batch)                                                              |
| `capabilities-and-ontology.md` with ❌/✅ pattern library   | Next commit                                                                              |
| `sdk/docs/llms.txt` + `llms-full.txt`                      | Next commit                                                                              |
| Fixture-file format spec + sample `docker-compose.dev.yml` | Next commit                                                                              |
| Konstera DevX MCP server (6-mini scope — catalogue tools)  | Next commit batch                                                                        |
| `konstera-agent init / dev / test / record / publish` CLI  | Separate work stream (ROADMAP track in `sdk/ROADMAP.md`)                                 |
| DevX MCP v2 (scaffold, fixture, manifest, scenario tools)  | After v1 lands + feedback                                                                |
| Claude Code `konstera-agent-dev` skill                     | Separate work stream — ships after the CLI is stable                                     |
| Browsable capability catalogue page on konstera.ai         | Separate work stream                                                                     |

---

## 11. Related reading

- **[end-to-end-journey.md](end-to-end-journey.md)** — the 13-phase lifecycle this doc specialises for LLM-driven dev.
- **[capabilities-and-ontology.md](capabilities-and-ontology.md)** — the pattern itself. ❌/✅ pairs. Required reading before writing any agent code.
- **[AGENTS.md](AGENTS.md)** — the scaffold template that every new agent project copies in.
- **[konstera.ai/resources/ontology-and-the-cost-of-change](https://konstera.ai/resources/ontology-and-the-cost-of-change)** — public article framing the pattern for buyers; good primer for a chat LLM pointed at it.
- **platform/docs/adr/013-agent-capabilities.md** — technical ADR for capability indirection.
- **platform/docs/adr/046-capability-indirection-dx-and-lock-in.md** — strategic framing + D4 commitment to LLM-ready docs.
- **wiki/concepts/capability-architecture.md** — comprehensive internal reference.
- **wiki/concepts/ontology.md** — Fragrance Shop refund scenario walkthrough.
