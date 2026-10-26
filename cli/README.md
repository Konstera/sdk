# Konstera CLI

The agent-authoring tool for the Konstera platform. Scaffold, validate, build, and deploy agents from the command line.

**Status**: v0.2 shipping. `konstera version`, `konstera manifest validate`, `konstera init`, `konstera build` all work today; `deploy` and `dev up/down` are stubbed and print the manual path. See [ROADMAP.md](../ROADMAP.md) and [Deferred commands](#deferred-commands-in-v01) below.

## Install

Once the first release ships, pick your platform:

```bash
# macOS + Linux
brew install konstera-ai/tap/konstera

# Windows
scoop bucket add konstera https://github.com/Konstera/scoop-bucket && scoop install konstera
winget install Konstera.CLI

# Direct download — pick the archive for your OS+arch
# https://github.com/Konstera/sdk/releases/latest
```

## From source

Requires Go 1.23+.

```bash
git clone https://github.com/Konstera/sdk.git
cd sdk/cli
go install ./cmd/konstera
konstera version
```

Or with `make`:

```bash
make build          # builds ./bin/konstera
make run ARGS="version"
make test
make release-snapshot  # GoReleaser dry-run (requires goreleaser installed)
```

## Current command surface

| Command | Status | What it does |
|---|---|---|
| `konstera version` | ✅ v0.1 | Print the CLI version + git SHA + build date. |
| `konstera manifest validate <path>` | ✅ v0.1 | Validate an agent manifest against the vendored `agent-manifest.v3.json` schema. Exits 0 on valid, 1 on invalid, with per-violation output grouped by JSON pointer. Use `--schema <path>` to point at a modified copy, or set `KONSTERA_SCHEMA_DIR`. |
| `konstera init <name>` | ✅ v0.2 | Scaffolds an agent in `python` / `typescript` / `dotnet` from embedded templates. v0.2 ships the `hello-world` template; `customer-service-starter` + `rag-starter` land in v0.3. Flags: `--language`, `--template`, `--dir`, `--force`. |
| `konstera build` | ✅ v0.2 | Shims `docker buildx build`. Reads id + version from manifest.json → default tag `<id>:<version>`. Flags: `--tag`, `--push`, `--platform`, `--context`, `--dockerfile`. |
| `konstera deploy` | 🚧 Stub | Will push the agent image + register the manifest with a workspace. For now, use the portal: Agents → Upload package. |
| `konstera dev up` / `konstera dev down` | 🚧 Stub | Will run the local Konstera dev stack (kernel + Postgres + your agent) via Docker Compose. For now, use the platform repo's compose stack. |

## Deferred commands

The following are declared in [ADR-035 §G](../../platform/docs/adr/035-public-developer-stack-and-repo-topology.md) but not implemented yet — they land in subsequent minor versions:

- `konstera login / logout / whoami / config` — auth + profile management
- `konstera llm add / providers / test` — BYOK provider setup
- `konstera invoke / invocation list / logs` — exercise + observe
- `konstera eval` — run the agent eval harness
- `konstera invocation trace / replay` — debugging workflows
- `konstera credential / connector / cost / metrics` — ops surfaces
- `konstera mcp serve` — expose the agent as a local MCP server for inline-agent-dev loops

## Technology

- **Go 1.23+** — chosen in [ADR-050](../../platform/docs/adr/050-cli-language-go.md) over .NET AoT + Rust + Node.js. Distribution via GoReleaser is the deciding factor.
- **Cobra** (`spf13/cobra`) for commands + flag parsing.
- **gojsonschema** (`xeipuuv/gojsonschema`) for `manifest validate` — swap-ready via the `internal/manifest` wrapper if we later switch to JSON Schema 2020-12 (`santhosh-tekuri/jsonschema`).
- **Charmbracelet** suite (bubbletea / bubbles / lipgloss) for TUI — added in v0.2 for `konstera dev up` live log tail.
- **GoReleaser** for release — single `.goreleaser.yml` → brew tap + scoop bucket + winget manifest + GitHub Release with per-platform archives.

## Repo layout

```
cli/
├── cmd/konstera/      — entry point (main.go)
├── internal/
│   ├── cmd/           — one file per Cobra command
│   ├── manifest/      — JSON Schema validator wrapper
│   └── version/       — version string (set by ldflags at build)
├── go.mod
├── Makefile           — dev shortcuts (build/test/lint/run/snapshot)
├── .goreleaser.yml    — release config
└── README.md
```

## Releasing

Tag + push triggers [`release-cli.yml`](../.github/workflows/release-cli.yml):

```bash
git tag cli-v0.1.0
git push origin cli-v0.1.0
```

See `PUBLISHING-RUNBOOK.md` at the Konstera project root for the pre-flight setup (Phase 5: Create `Konstera/homebrew-tap` + `Konstera/scoop-bucket` + add `HOMEBREW_TAP_GITHUB_TOKEN` + `SCOOP_BUCKET_GITHUB_TOKEN` secrets).

## Design decisions

- **[ADR-050](../../platform/docs/adr/050-cli-language-go.md)** — Why Go over .NET AoT, Rust, and Node.js.
- **[ADR-035](../../platform/docs/adr/035-public-developer-stack-and-repo-topology.md)** — Scope + command surface preview.

## Contributing

Standard Go workflow: `go test ./...` + `golangci-lint run ./...` must pass. Follow the Cobra command pattern established in `internal/cmd/` — one file per top-level command, nested subcommands co-located.

## License

Apache-2.0. See repo root `LICENSE`.
