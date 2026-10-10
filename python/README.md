# konstera-sdk (Python)

Build Konstera agents in Python without hand-writing MCP client boilerplate, HTTP servers, or env-var parsing. Subclass `Agent`, override `handle()`, call `run()`.

**Status**: v0.1.0 (M6). Log + LLM (stub) kernel services only. Vector / state / credentials / cost / tool / agents / human / prompt come in M7.

## Install

The SDK ships as a Python package. During development, install from source:

```bash
pip install -e sdk/python
```

Container agents install it via a multi-stage Dockerfile — the SDK wheel is built in one stage and copied into the final image. See `agents/hello-world-python/Dockerfile` for the reference pattern.

## Minimal agent

```python
from konstera_sdk import Agent, AgentContext, AgentRequest, AgentResponse, run

class HelloAgent(Agent):
    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        name = req.input.strip() or "world"
        await ctx.log.info(f"Hello, {name}!", input=name, language="python")
        return AgentResponse(content=f"Hello, {name}!")

if __name__ == "__main__":
    run(HelloAgent())
```

That's it — ~10 lines for a complete agent. `run()` handles:

- Reading `KONSTERA_KERNEL_MCP_URL`, `KONSTERA_AGENT_INSTANCE_ID`, `KONSTERA_AGENT_ID`, `KONSTERA_AGENT_VERSION` from the environment (injected by the kernel's `ContainerAgentHost`)
- Setting up the MCP client back to the kernel
- Hosting `/health`, `/describe`, `/invoke` on port 8080
- Routing invocations to your `handle()`
- Graceful shutdown

## API

### `Agent` (base class)

```python
class Agent:
    async def initialize(self, ctx: AgentContext) -> None: ...
    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse: ...
    async def shutdown(self, ctx: AgentContext) -> None: ...
```

Override `handle()` (required). Override `initialize()` / `shutdown()` for setup/teardown.

### `AgentContext`

```python
ctx.instance_id     # str — this agent instance's UUID
ctx.agent_id        # str — e.g. "io.konstera.hello-world-python"
ctx.agent_version   # str — e.g. "0.1.0"
ctx.log             # LogService — ctx.log.info/warn/error
ctx.llm             # LlmService — ctx.llm.complete (stub in M6)
```

### `LogService`

```python
await ctx.log.info(message, **fields)
await ctx.log.warn(message, **fields)
await ctx.log.error(message, **fields)
```

Structured fields (kwargs) are JSON-serialised and enriched by the kernel with tenant/instance/invocation context, then flowed to Serilog + App Insights.

### `LlmService` (stub in M6)

```python
text = await ctx.llm.complete(model="claude-sonnet-4-6", prompt="Hello")
```

Real Claude / OpenAI / Gemini adapters land in M10 (SPEC §10). Interface is stable now; agent code written today will keep working when the stub goes away.

### `run(agent, port=8080)`

Blocks until the process is stopped. Handles all lifecycle: reads env, creates context, calls `initialize()`, serves HTTP, calls `shutdown()` on SIGTERM.

## Direct-run mode

When `KONSTERA_KERNEL_MCP_URL` is unset, kernel callbacks become no-ops (they log a warning and return successfully). This lets you develop agents locally without the full Konstera stack running:

```bash
python -m your_agent_module
# Serves on :8080 — POST /invoke works but ctx.log/ctx.llm skip.
```

## Licence

BSL-1.1 (Business Source License). See the repo-level `LICENSE`. Auto-converts to Apache 2.0 four years after each release.
