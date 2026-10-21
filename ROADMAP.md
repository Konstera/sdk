# Konstera SDK — Roadmap

> **Status:** The SDK repo has five packages across three registries, with release pipelines ready to publish on tag push. First publishes are gated on repo-admin registry setup (NuGet API key, PyPI trusted publishers, npm token — see [`RELEASING.md`](./RELEASING.md)). The full **agent SDK** exists in .NET (v0.1.0) and Python (v0.5.0); the TypeScript equivalent is scaffolded but not yet implemented.

Last updated: 2026-10-21.

## Legend

- 🟢 **Now** — committed, blocking v1 real-user adoption
- 🟡 **Next** — Phase 2, extends what v1 does
- 🔵 **Later** — big-ticket future work

---

## 1. Package publishing (🟢 Now — **pipelines ready**, awaiting registry setup)

The source for all five packages is in-tree, builds green, release workflows are shipped and awaiting the first tag push. **Blocker: one-time registry setup** (API keys / trusted publishers) — see [`RELEASING.md`](./RELEASING.md).

- [x] **NuGet publish pipeline** for `Konstera.Sdk` + `Konstera.Sdk.Contexts` — [`.github/workflows/release-dotnet.yml`](./.github/workflows/release-dotnet.yml). Tag: `sdk-dotnet-v*` + `sdk-dotnet-contexts-v*`. Secret: `NUGET_API_KEY`.
- [x] **PyPI publish pipeline** for `konstera-sdk` + `konstera-sdk-contexts` — [`.github/workflows/release-python.yml`](./.github/workflows/release-python.yml). Tag: `sdk-python-v*` + `sdk-python-contexts-v*`. Auth: GitHub OIDC trusted publisher (no long-lived token).
- [x] **npm publish pipeline** for `konstera-sdk-contexts` — [`.github/workflows/release-typescript.yml`](./.github/workflows/release-typescript.yml). Tag: `sdk-ts-contexts-v*`. Secret: `NPM_TOKEN` (classic token for first publish; migrate to OIDC post-first-publish).
- [x] **Semver policy** documented in [`RELEASING.md`](./RELEASING.md) + this file §semver below.
- [x] **Release-tag convention** fixed and documented in [`RELEASING.md`](./RELEASING.md).
- [ ] **Repo-admin one-time setup** (not code — gates all first publishes):
  - Create `NUGET_API_KEY` secret
  - Configure PyPI pending publishers for `konstera-sdk` + `konstera-sdk-contexts`
  - Create GitHub Environment named `pypi`
  - Create `NPM_TOKEN` secret
- [ ] **First publishes** — push the first tags and verify end-to-end:
  - `sdk-dotnet-v0.1.0`, `sdk-dotnet-contexts-v1.0.0`
  - `sdk-python-v0.5.0`, `sdk-python-contexts-v1.0.0`
  - `sdk-ts-contexts-v1.0.0`

## 2. Generator CI gate (🟢 Now — **shipped**)

The generator script (`scripts/generate_constants.py`) is the single-source-of-truth guard, enforced by CI.

- [x] CI job: `python scripts/generate_constants.py && git diff --exit-code` fails the build if any generated file is out of sync with the pack JSON — [`.github/workflows/sdk-check.yml`](./.github/workflows/sdk-check.yml) `generator-drift` job.
- [x] Release-time drift gate (defence-in-depth): the release-dotnet / release-python / release-typescript workflows for context packs re-run the generator and fail if drift is detected (prevents a bad tag publishing stale constants even if someone bypassed the PR CI).
- [ ] Schema-shape check — the pack JSON validates against a companion `standard-context-pack-v1.schema.json` (write this file).
- [ ] Cross-package version lockstep — all three contexts packages must share the same `MAJOR.MINOR` as the pack.

## 3. Drift check with platform's vendored copy (🟢 Now)

Platform (`platform/schemas/standard-context-pack-v1.json` on ADO) is a hand-vendored copy of this repo's `schemas/standard-context-pack-v1.json`. Right now nothing enforces the two staying in sync.

- [ ] Scheduled GitHub Actions job (nightly): download `platform/schemas/*.json` via ADO REST API, byte-compare, fail on diff
- [ ] Same gate for `agent-manifest.v3.json`
- [ ] Platform-side ADO pipeline: fail Platform's build if `platform/schemas/*.json` has drifted from the SDK release tagged in `platform/schemas/.version` (write this file to track the vendored SDK version)

## 4. TypeScript agent SDK (🟡 Next)

The `sdk/typescript/` folder is scaffolded; `konstera-sdk-contexts` is the only package today. The full agent SDK — the actual MCP wrapper agent authors program against — is still TODO.

- [ ] **`sdk/typescript/packages/konstera-sdk/`** — mirror of `sdk/python/src/konstera_sdk/`
  - `Agent` + `run()` entry point
  - `AgentContext` with sub-services:
    - `ctx.llm` — chat completions, metered via kernel
    - `ctx.vector` — RAG retrieval
    - `ctx.state` — tenant-scoped key/value
    - `ctx.cost` — manual spend reporting
    - `ctx.log` — structured logging
    - `ctx.credentials` — connector OAuth tokens
    - `ctx.tool` — kernel-exposed tools catalog
    - `ctx.agents` — invoke sibling agents (child workflows)
    - `ctx.human` — in-the-loop decisions (Temporal signals)
    - `ctx.prompt` — centralised prompt templates
    - `ctx.context` — ADR-037 glossary / skills / ontology lookups
    - `ctx.capability` — purpose-first indirection over connectors (ADR-013)
    - `ctx.connector` — direct connector handles
    - `ctx.rule` — business-rule registry
    - `ctx.artifact` — content-addressed blob store
  - MCP client/server using `@modelcontextprotocol/sdk`
  - `/health`, `/describe`, `/invoke` HTTP endpoints (minimal Node server, Fastify or raw `http`)
  - Dual ESM + CJS build
- [ ] **`sdk/typescript/packages/konstera-sdk-manifest/`** — Zod schemas for the v3 agent manifest + inferred TypeScript types
- [ ] **End-to-end validator**: write a `agents/hello-world-typescript` reference agent in the `agents/` sibling repo that depends on `konstera-sdk` + `konstera-sdk-contexts` via `npm link` during dev, then via `npm install` once published. Verify kernel-side `IAgentHost` sees it exactly like the .NET / Python counterparts.
- [ ] pnpm workspace at `sdk/typescript/` root (shared `tsconfig.base.json`, cross-package versioning via Changesets)

## 5. ADR-036 §B unblock — agents/ migrates from ProjectReference → PackageReference (🟡 Next)

The agents repo (`agents/`) currently references the .NET SDK via `<ProjectReference>` and the Python SDK via a relative path (`../sdk/python/`). ADR-036 commits to published-package references once the SDKs ship to NuGet / PyPI. This cannot happen until **§1 Package publishing** lands.

- [ ] After NuGet publish: `agents/hello-world-dotnet/` → `<PackageReference Include="Konstera.Sdk" Version="0.6.0" />`
- [ ] After PyPI publish: agent `pyproject.toml` / `Dockerfile` → `pip install konstera-sdk==0.6.0` (instead of `COPY ../sdk/python/`)
- [ ] After npm publish: same for `agents/hello-world-typescript/` (after §4)

## 6. Standard Context Pack v2 (🟡 Next)

Pack v1 is a retail-wedge-tight 24+2+24. The real value starts when it covers the whole business.

- [ ] **HR domain** (~15 terms): `headcount`, `attrition_rate`, `promotion_rate`, `utilization`, `time_to_hire`, `offer_acceptance_rate`, `training_cost_per_fte`, `voluntary_attrition`, `involuntary_attrition`, `salary_band`, `comp_ratio`, `tenure`, `span_of_control`, `pto_balance`, `headcount_plan`
- [ ] **Finance domain** (~10 terms): `dso`, `dpo`, `working_capital`, `ebitda`, `free_cash_flow`, `cash_burn`, `runway_months`, `accruals`, `prepayments`, `deferred_revenue`
- [ ] **Marketing domain** (~10 terms): `cpa`, `roas`, `mql`, `sql`, `bounce_rate`, `open_rate`, `click_through_rate`, `conversion_rate`, `attribution_window_days`, `funnel_stage`
- [ ] **5 reference skills** matching the above domains (`forecast_demand`, `diagnose_cash_burn_spike`, `score_marketing_qualified_lead`, `tier_customer_by_ltv`, `recommend_hiring_plan_adjust`)
- [ ] **~20 more ontology entities** (`employee`, `role`, `department`, `invoice`, `bill`, `payment`, `budget_line`, `campaign`, `ad_group`, `creative`, …)
- [ ] Ship as `sdk/schemas/standard-context-pack-v2.json`; packages bump to `2.0.0` (not strictly breaking since v1 names remain, but major-version signals the catalogue expansion)
- [ ] Deprecation policy: v1 supported for 12 months after v2 GA

## 7. `sdk/cli/` — the `konstera` developer CLI (🔵 Later)

Per ADR-035, `sdk/cli/` is reserved for the public `konstera` CLI. The folder exists today but is empty.

- [ ] **Technology:** .NET 10 AoT single-file binary (per ADR-035) — cross-compiles to Windows / macOS / Linux x64 + arm64
- [ ] **Auth:** `konstera auth login` — device-code OAuth against the tenant's portal; stores refresh token in OS keychain
- [ ] **Scaffold:** `konstera new agent <name> --language dotnet|python|typescript` — generates a working minimum agent from a template
- [ ] **Validate:** `konstera validate ./manifest.yaml` — client-side manifest schema check against the vendored `agent-manifest.v3.json`
- [ ] **Build:** `konstera build` — wraps `docker buildx` with the Konstera-standard labels (`io.konstera.*`)
- [ ] **Deploy:** `konstera deploy` — manifest validation + image push + install into the connected tenant
- [ ] **Test:** `konstera test ./scenarios/*.yaml` — scenario-driven local invocations against a running kernel
- [ ] **Logs/traces:** `konstera logs <workflow-id>`, `konstera trace <workflow-id>` — surface Temporal workflow state via the kernel's admin API
- [ ] Smoke-test as part of the SDK release pipeline

## 8. Documentation and ergonomics (🔵 Later)

The published packages reference `konstera.example` placeholder URLs today. Replace with real hosted docs.

- [ ] **Hosted docs site** at `docs.konstera.ai` or similar (likely a Starlight / Mintlify / docusaurus app, SSG-rendered off `sdk/docs/`)
- [ ] **"Build an agent in 10 lines"** quickstart for each language (NuGet, PyPI, npm)
- [ ] **API reference** auto-generated from source: DocFX for .NET, pdoc / sphinx for Python, TypeDoc for TypeScript
- [ ] **Migration guide:** legacy `Konstera.Agents.Sdk` (platform-internal, deprecated) → `Konstera.Sdk` (public)
- [ ] **ADR-013 capability-first pattern** worked example — building a connector-agnostic agent that uses `ctx.capability.email_send` without knowing which provider is bound
- [ ] **Reference agents repo** linked from each package's README — a living catalogue of production patterns

## 9. SDK <-> Platform parity audit (🔵 Later)

The three SDKs should expose the same kernel services. Known gaps today:

- [ ] **MCP services exposed to agents (reference catalogue in `platform/docs/SPEC.md §7`):** `llm`, `vector`, `state`, `credentials`, `cost`, `log`, `tool`, `agents`, `human`, `prompt`, `context`, `capability`, `connector`, `rule`, `artifact` — audit each SDK confirms each is wrapped
- [ ] **Python SDK** currently at `0.9.0` with capability indirection (ADR-013) shipped; **`.NET SDK`** at `0.1.0`-ish and may lag — version-align the two
- [ ] **End-to-end parity test:** run the same reference agent against the kernel in all three languages, assert identical observed behaviour (same emitted MCP calls, same recorded `usage_events`, same `AgentResponse`)

## 10. Governance (🔵 Later)

Once the SDK has external consumers, the breakage blast-radius grows.

- [ ] **Semver policy document** (`docs/semver.md`) formalising the "names" / "shape" / "behaviour" categories
- [ ] **Deprecation policy** — minimum N-month overlap window for removed names / methods; `@deprecated` annotations with target removal version
- [ ] **Breaking-change migration-guide template** for every major bump
- [ ] **Security disclosure process** — vulnerability reporting path, embargo policy, published advisory feed
- [ ] **Public changelog** (`CHANGELOG.md`) auto-generated by Changesets (TypeScript) / release-please / manual (dotnet, python)

---

## Dependencies

```
                    ┌────────────────────────────────────────┐
                    │   1. Package publishing (NuGet/PyPI/npm) │
                    └────────────┬───────────────────────────┘
                                 │ unblocks
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
  5. agents→Package Ref    6. Pack v2 release    7. sdk/cli deploy
                                 │
                                 ▼
                       4. TypeScript full agent SDK
                                 │
                                 ▼
                       end-to-end TS agent in agents/
```

2 (CI gate) and 3 (drift check) are independent and can land anytime.

## Owned by

Updated as commitments are made. Right now all tracks are unowned.

---

*This file is maintained manually. Each 🟢 Now item should either be in flight on a feature branch or have a concrete reason it's not.*
