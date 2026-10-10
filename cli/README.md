# Konstera CLI

> **Status: planned — not yet implemented.** Lands in Phase 2 of the developer-stack roadmap (target: 2026-11-07).

The Konstera CLI (`konstera`, aliased as `kn`) is the build/deploy/observe tool for agent authors. It wraps the platform's HTTP + MCP surface so building, testing, and shipping an agent is a short sequence of commands rather than a multi-step runbook.

See:
- [ADR-035](../../docs/adr/035-public-developer-stack-and-repo-topology.md) — design and scope decisions
- [Developer-stack roadmap](../../docs/roadmap/developer-stack-2026Q4-Q1.md) — delivery phases
- Command surface preview — ADR-035 §G

## Planned command groups (v0.1)

```
konstera login / logout / whoami / config               # auth + profiles
konstera llm add / providers / test                     # BYOK provider setup
konstera init --template <t>                            # scaffold agent
konstera manifest validate                              # check against schema
konstera build / push / deploy                          # ship an agent
konstera invoke / invocation list / logs                # exercise + observe
konstera dev                                            # local run (compose-based v0.1)
```

Later phases add `eval`, `invocation trace/replay`, `credential`, `connector`, `cost`, `metrics`, `mcp serve`.

## Technology

- .NET 10 AoT single-file publish
- Spectre.Console for terminal UX
- Distributed via brew / scoop / winget / GitHub Releases
- Config in `~/.konstera/config.yaml`; secrets in OS keychain

## Repo layout (when code lands)

```
sdk/cli/
├── src/Konstera.Cli/              # command classes
├── src/Konstera.Cli.DevKernel/    # Phase 4: embedded mini-kernel
├── tests/Konstera.Cli.Tests/
├── Konstera.Cli.slnx
└── README.md
```
