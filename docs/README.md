# Konstera public developer docs

> **Status: Phase 1 scope.** Getting-started path lands with SDK v0.1 (target: 2026-10-16).

These docs are the public developer-facing documentation for agent authors. They ship with `konstera-sdk` when the public repo splits out.

**Audience:** developers writing agents to run on Konstera. **Not** platform engineers, **not** operators installing Konstera — those readers are served by `konstera-platform/docs/` (internal) and `konstera-deploy/docs/` (future repo) respectively.

## Planned pages (Phase 1)

- `getting-started.md` — install SDK, scaffold agent, build + run manually (CLI docs land Phase 2)
- `concepts.md` — what an agent is, how invocations work, kernel services (MCP), tenants
- `sdk-reference-dotnet.md` — `IAgent`, `AgentContext`, kernel service clients
- `sdk-reference-python.md` — same, Pythonic surface
- `manifest-reference.md` — annotated walk-through of `agent-manifest.v3.json`
- `mcp-callbacks.md` — what the kernel exposes (`llm`, `vector`, `state`, `credentials`, `cost`, `log`, `tool`, `agents`, `human`, `prompt`)

## Planned pages (Phase 2+)

- `cli-reference.md` — auto-generated from CLI command definitions
- `local-dev.md` — the `konstera dev` loop
- `cli-sdk-compatibility.md` — which CLI version supports which SDK version

## Planned pages (Phase 3+)

- `eval-guide.md` — writing eval cases, LLM-as-judge, regression testing
- `ci-cd.md` — using the GH Actions + ADO templates in `sdk/ci-templates/`
- `cookbook/` — recipes per common pattern (RAG, HiL, scheduled, webhook, multi-agent)

## Related

- [ADR-035](../../docs/adr/035-public-developer-stack-and-repo-topology.md) — public developer stack decisions
- [Developer-stack roadmap](../../docs/roadmap/developer-stack-2026Q4-Q1.md) — delivery phases
