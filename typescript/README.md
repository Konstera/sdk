# Konstera TypeScript SDK

Public TypeScript / Node.js packages for building Konstera agents.

## Current packages

| Package | Status | Description |
|---------|--------|-------------|
| [`@konstera/sdk-contexts`](./packages/konstera-sdk-contexts) | shipped (v1.0.2) | Typed constants for the Konstera Standard Context Pack v1 — reference canonical names without magic strings |
| [`@konstera/sdk`](./packages/konstera-sdk) | shipped (v0.4.4) | The agent SDK — MCP client/server wrapper, `AgentContext` ergonomics (mirror of `konstera-sdk` on PyPI and `Konstera.Sdk` on NuGet) |
| `konstera-sdk-manifest` | planned | Zod schema + TypeScript types for the v3 agent manifest |

## Why TypeScript as the third SDK

Konstera agents speak **MCP** (Model Context Protocol). The MCP reference implementation is itself TypeScript — `@modelcontextprotocol/sdk` is the project's canonical SDK, and the broader AI-agent-dev ecosystem (LangGraph.js, Vercel AI SDK, Mastra, OpenAI Agents SDK, Anthropic SDK) is TS-first. Shipping `@konstera/sdk` for TS gives agent authors a drop-in third-language choice next to .NET and Python, with the same wire protocol and manifest schema.

See the sibling [`dotnet/`](../dotnet) and [`python/`](../python) SDKs for conceptual parity.

## Layout

This folder is a **pnpm workspace** (planned once the agent SDK lands). For now it's a single-package npm folder:

```
typescript/
├── packages/
│   └── konstera-sdk-contexts/
│       ├── src/
│       │   ├── index.ts
│       │   └── generated.ts  (do not edit — see sdk/scripts/generate_constants.py)
│       ├── scripts/copy-pack.mjs
│       ├── package.json
│       ├── tsconfig.json
│       └── README.md
```

## License

All packages Apache-2.0 per ADR-035.
