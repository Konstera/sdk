<img src="https://raw.githubusercontent.com/Konstera/sdk/main/assets/brand/konstera-mark-blue.png" alt="Konstera" width="64" />

# @konstera/sdk (TypeScript)

Build Konstera agents in TypeScript without hand-writing MCP client boilerplate, HTTP servers, or env-var parsing. Subclass `Agent`, override `handle()`, call `run()`.

**Status**: v0.1.0 (proof of life). Log + LLM kernel services. The other 13 services (state, vector, credentials, cost, tool, agents, artifact, human, rule, connector, capability, context, semantic) land in v0.2.0.

Mirror of [`konstera-sdk` (Python)](../../python/) at the same conceptual API, idiomatic TypeScript.

## Install

```bash
npm install @konstera/sdk
```

## Minimal agent

```typescript
import { Agent, AgentContext, AgentRequest, AgentResponse, run } from "@konstera/sdk";

class HelloAgent extends Agent {
  async handle(req: AgentRequest, ctx: AgentContext): Promise<AgentResponse> {
    const name = req.input.trim() || "world";
    await ctx.log.info(`Hello, ${name}!`, { input: name, language: "typescript" });
    return { content: `Hello, ${name}!` };
  }
}

run(new HelloAgent());
```

That's it — ~10 lines for a complete agent. `run()` handles:

- Reading `KONSTERA_KERNEL_MCP_URL`, `KONSTERA_AGENT_INSTANCE_ID`, `KONSTERA_AGENT_ID`, `KONSTERA_AGENT_VERSION`, `KONSTERA_TENANT_ID` from the environment (injected by the kernel's `ContainerAgentHost`)
- Setting up the MCP client back to the kernel
- Hosting `/health`, `/describe`, `/invoke` on port 8080
- Routing invocations to your `handle()`
- Graceful shutdown on `SIGTERM` / `SIGINT`

## API

### `Agent` (base class)

```typescript
abstract class Agent {
  initialize(ctx: AgentContext): Promise<void>;
  handle(req: AgentRequest, ctx: AgentContext): Promise<AgentResponse>;
  shutdown(ctx: AgentContext): Promise<void>;
}
```

Override `handle()` (required). Override `initialize()` / `shutdown()` for setup/teardown.

### `AgentContext`

```typescript
interface AgentContext {
  readonly instanceId: string;      // this agent instance's UUID
  readonly tenantId: string;        // tenant UUID
  readonly agentId: string;         // e.g. "io.konstera.hello-world-typescript"
  readonly agentVersion: string;    // e.g. "0.1.0"
  readonly log: LogService;
  readonly llm: LlmService;
}
```

### `LogService`

```typescript
await ctx.log.info(message, fields);
await ctx.log.warn(message, fields);
await ctx.log.error(message, fields);
```

Structured fields are JSON-serialised and enriched by the kernel with tenant/instance/invocation context.

### `LlmService`

```typescript
const result = await ctx.llm.complete({
  model: "claude-sonnet-4-6",
  prompt: "Hello",
  maxTokens: 100,
});
console.log(result.text, result.usage);
```

Returns `LlmResult { text, usage: { inputTokens, outputTokens, costUsd } }`.

### `run(agent, options?)`

Blocks until `SIGTERM` / `SIGINT`. Handles the full lifecycle: reads env, creates context, calls `initialize()`, serves HTTP, calls `shutdown()` on signal.

```typescript
run(new HelloAgent(), { port: 8080 });  // port defaults to 8080
```

## Direct-run mode

When `KONSTERA_KERNEL_MCP_URL` is unset, kernel callbacks become no-ops (log a warning + return successfully). This lets you develop agents locally without the full Konstera stack:

```bash
node dist/your-agent.js
# Serves on :8080 — POST /invoke works, ctx.log.* / ctx.llm.* skip the kernel call.
```

Useful for:

- Unit testing the agent class with mocked `AgentContext`
- Running the agent in a container without a kernel for smoke tests
- IDE-driven dev loops before the full stack is up

## Build

```bash
pnpm install           # from typescript/ workspace root
pnpm --filter @konstera/sdk run build
```

Dual ESM + CJS output in `dist/`.

## Test

```bash
pnpm --filter @konstera/sdk run test
```

## Licence

BSL-1.1 (Business Source License). See the repo-level `LICENSE`. Auto-converts to Apache 2.0 four years after each release.
