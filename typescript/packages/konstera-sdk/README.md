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
  readonly browser: BrowserService; // kernel-hosted browser sessions (0.5.0)
  // ... plus state, vector, credentials, cost, tool, agents, artifact,
  // human, rule, connector, capability, semantic
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

### `BrowserService` (0.5.0)

```typescript
await using page = await ctx.browser.openSession("amazon_uk");
await page.navigate("https://www.amazon.co.uk/gp/css/order-history");
await page.typeSecret("#ap_email", "username");    // typed by reference
await page.handoffToHuman("CAPTCHA shown", { untilUrlContains: "order-history" });
const rows = await page.extract(".order-card", { id: { selector: ".order-id" } });
```

Sessions run in a browser the kernel controls, against a connection granted to the agent, usually a **Website login** connection (site, username, password, optional authenticator key, optional extra fields such as `pin`). `typeSecret` names a secret field of the connection (`username`, `password`, `totp`, or an extra field such as `pin`); the kernel types the value, only on the connection's own site, so secrets never reach agent code. Send CAPTCHA, passkey prompts and any challenge the agent does not recognise to `handoffToHuman`. There is no CAPTCHA solving. `await using` closes the session when the scope exits (a close failure there is logged, not thrown); or call `page.close()` yourself.

| Method | Kernel tool | Returns |
|---|---|---|
| `ctx.browser.openSession(alias)` | `browser_open_session` | `BrowserSession` (`sessionId`, `connection`) |
| `navigate(url, waitUntil = "load")` | `browser_navigate` | `{ url, title }` |
| `click(selector, { timeoutSeconds = 15 })` | `browser_click` | `void` |
| `type(selector, text, { timeoutSeconds = 15 })` | `browser_type` | `void` (plain, non-secret text only) |
| `typeSecret(selector, secretField)` | `browser_type_secret` | `void` |
| `waitFor({ selector, urlContains, timeoutSeconds = 30 })` | `browser_wait_for` | `{ matched, url }` |
| `exists(selector)` | `browser_exists` | `{ exists, count }` |
| `text(selector)` | `browser_text` | `string \| null` |
| `extract(rowSelector, { name: { selector, attr?, all? } })` | `browser_extract` | rows |
| `screenshot(label)` | `browser_screenshot` | PNG `Buffer` |
| `handoffToHuman(reason, { untilSelector, untilUrlContains, timeoutSeconds = 300 })` | `browser_handoff_to_human` | `{ resolved, url }` |
| `close()` | `browser_close_session` | `void` (idempotent) |

Every browser call throws in direct-run mode (no kernel), and throws with the kernel's message when a tool fails.

### `AgentFailure` (0.5.0)

```typescript
import { AgentFailure } from "@konstera/sdk";

throw new AgentFailure("The site refused the sign-in; check the connection.", {
  category: "action_needed",
});

// or a subclass with its own default
class SignInRefused extends AgentFailure {
  static override readonly defaultCategory = AgentFailure.ACTION_NEEDED;
}
```

Uncategorised errors are recorded as `agent_bug`. Throw `AgentFailure` (or subclass it, or give your error a string `category` property) when the cause is outside your code: `dependency_failure` (the default; an outside system refused or failed), `action_needed` (a person must act first; not retried), `input_invalid`, `credential_missing`. The runtime returns it in the `/invoke` error body as `{"error": {"type", "message", "category"}}`, the same as the Python SDK.

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

Apache-2.0. See the repo-level [`LICENSE`](https://github.com/Konstera/sdk/blob/main/LICENSE).
