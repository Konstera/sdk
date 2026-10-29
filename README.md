# Konstera SDK

The public developer surface for building **AI agents that run on Konstera** — the platform where every AI agent in your business runs.

Agents are **OCI container images speaking the Model Context Protocol (MCP)**. This repo gives you three language SDKs that wrap MCP so you can subclass `Agent`, override `handle()`, and ship a container — without hand-writing MCP client boilerplate, HTTP servers, or env-var parsing.

Full docs at **[konstera.ai/docs](https://konstera.ai/docs)**. This README is the map of this repo.

## Pick your language

| Language | Package | Install | Minimal agent |
|---|---|---|---|
| **Python** | [`konstera-sdk`](./python/) · PyPI | `pip install konstera-sdk` | [python/README.md](./python/README.md) |
| **TypeScript** | [`@konstera/sdk`](./typescript/) · npm | `npm add @konstera/sdk` | [typescript/README.md](./typescript/README.md) |
| **.NET** | [`Konstera.Sdk`](./dotnet/) · NuGet | `dotnet add package Konstera.Sdk` | [dotnet/README.md](./dotnet/README.md) |

All three cover the same **14 kernel services** (`log`, `llm`, `state`, `vector`, `credentials`, `cost`, `tool`, `agents`, `artifact`, `human`, `rule`, `connector`, `capability`, `semantic`) with identical shape and graceful-degradation semantics. Pick whichever runtime fits your team.

The Python SDK also has `browser` (kernel-hosted browser sessions over a granted connection; secrets typed by reference). TypeScript and .NET follow later.

## What else is here

```
sdk/
├── python/              # konstera-sdk (Python) + konstera-sdk-contexts
├── typescript/          # @konstera/sdk + @konstera/sdk-contexts (pnpm workspace)
├── dotnet/              # Konstera.Sdk + Konstera.Sdk.Contexts (dotnet 10)
├── cli/                 # konstera CLI (.NET 10 AoT; planned Phase 2)
├── devx-mcp/            # @konstera/devx-mcp — MCP server exposing the capability catalogue
├── schemas/             # agent-manifest.v3.json + standard-context-pack-v1.json (single source of truth)
├── docs/                # developer-stack roadmap + ADR links (public-facing docs live at konstera.ai/docs)
├── examples/            # end-to-end example agents (one per language)
├── scripts/             # cross-package tooling (constants generator, drift gate)
├── RELEASING.md         # how to publish each package
└── ROADMAP.md           # delivery phases + semver policy
```

## Standard Context Pack

Alongside each language SDK ships a **typed-constants companion** so agents reference `ContextTerms.OrderStatus.Shipped` rather than magic strings:

| Package | Install |
|---|---|
| `konstera-sdk-contexts` (PyPI) | `pip install konstera-sdk-contexts` |
| `@konstera/sdk-contexts` (npm) | `npm add @konstera/sdk-contexts` |
| `Konstera.Sdk.Contexts` (NuGet) | `dotnet add package Konstera.Sdk.Contexts` |

All three share the same `MAJOR.MINOR` as the source JSON in `schemas/standard-context-pack-v1.json`. A CI drift-gate in `sdk-check.yml` catches un-regenerated constants on PR.

## DevX MCP server

**`@konstera/devx-mcp`** — an MCP server that lets Claude Code, Cursor, Windsurf, and Claude Desktop query the Konstera capability catalogue inline. Three tools: `catalogue_list_capabilities`, `catalogue_get_capability`, `catalogue_search`. Install snippets for all four clients in [devx-mcp/README.md](./devx-mcp/README.md).

## Konstera CLI (planned Phase 2)

**`konstera`** (aliased `kn`) — the build / test / deploy / observe tool. Planned command surface:

```
konstera login / logout / whoami / config               # auth + profiles
konstera llm add / providers / test                     # BYOK provider setup
konstera init --template <t>                            # scaffold agent
konstera manifest validate                              # check against schema
konstera build / push / deploy                          # ship an agent
konstera invoke / invocation list / logs                # exercise + observe
konstera dev                                            # local run (compose-based v0.1)
```

Target: 2026-11-07. Distributed via brew / scoop / winget / GitHub Releases + as a `dotnet tool`. See [cli/README.md](./cli/README.md) for scope + status.

## Build an agent — the three files

Every Konstera agent ships with the same three files:

1. **The handler** — `main.py` / `Program.cs` / `index.ts` — subclass `Agent`, override `handle()`.
2. **The manifest** — `manifest.json` — an [`agent-manifest.v3.json`](./schemas/agent-manifest.v3.json) instance declaring what capabilities the agent needs + what panels reviewers see.
3. **The Dockerfile** — multi-stage build; agents ship as OCI container images.

Walk through [the SDK quickstart](https://konstera.ai/docs/sdk-quickstart) for the full file contents in each language, or clone one of the reference agents in the sibling [`Konstera/agents`](https://github.com/Konstera/agents) repo.

## Reference agents

Working templates + end-to-end tests of the SDK, published in [`Konstera/agents`](https://github.com/Konstera/agents):

- `hello-world-{python,dotnet,typescript}` — minimum shape, one `handle()` method
- `prepayments-agent` — retail finance; evidence → rule → classify → schedule → approval
- `psp-reconciliation-agent` — PSP settlement vs orders, 3-way match + 8 discrepancy types
- `customer-service-agent` — full CS with ontology + glossary + eval harness

## Contributing

- Everything in this repo is **Apache-2.0** licensed ([ADR-035](https://github.com/Konstera/platform/blob/develop/platform/docs/adr/035-public-developer-stack-and-repo-topology.md)).
- Changes land via PR to `main`. CI runs on every PR (`.github/workflows/sdk-check.yml`).
- Breaking SDK changes → MAJOR version bump → downstream agents update as an explicit PR ([ADR-036](https://github.com/Konstera/platform/blob/develop/platform/docs/adr/036-polyrepo-via-published-packages.md)).
- Publishing is tag-triggered — see [RELEASING.md](./RELEASING.md) for the exact tag → registry map and one-time secret setup.

## Related repos

- **[Konstera/agents](https://github.com/Konstera/agents)** — reference agent implementations
- **[Konstera/deploy](https://github.com/Konstera/deploy)** — Helm chart + Compose tarball for self-hosting
- **[konstera.ai/docs](https://konstera.ai/docs)** — public developer documentation (the SDK's primary surface for external agent authors)

## License

Everything in this repository is licensed under the [Apache License 2.0](./LICENSE): the SDKs (`Konstera.Sdk`, `konstera-sdk`, `@konstera/sdk`), the context packs (`Konstera.Sdk.Contexts`, `konstera-sdk-contexts`, `@konstera/sdk-contexts`), `@konstera/devx-mcp`, `cli/`, `schemas/`, `examples/` and `scripts/`.

The SDKs are Apache-2.0 so anyone can build, run and ship agents on Konstera without licence friction.
