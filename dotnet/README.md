# Konstera Agent SDK for .NET

Mirror of `sdk/python`. Same conceptual API (`Agent` → `HandleAsync` →
`AgentResponse`), idiomatic C#. Wraps the MCP callback protocol and the
`/invoke` HTTP contract so agent authors write business logic, not plumbing.

## Minimal agent

```csharp
using Konstera.Sdk;

AgentRuntime.Run(new HelloAgent());

public sealed class HelloAgent : Agent
{
    public override async Task<AgentResponse> HandleAsync(
        AgentRequest req, AgentContext ctx, CancellationToken ct)
    {
        await ctx.Log.InfoAsync($"Hello, {req.Input}!", ct: ct);
        return new AgentResponse { Content = $"Hello, {req.Input}!" };
    }
}
```

That's it. `AgentRuntime.Run` reads `KONSTERA_KERNEL_MCP_URL` and the
`KONSTERA_AGENT_*` env vars the kernel injects at container-create time,
opens an MCP session back to the kernel, and hosts your agent as an HTTP
server exposing `/health`, `/describe`, and `/invoke`.

## Kernel services

Every service is a property on `AgentContext`. All hit the kernel via MCP
callbacks — the kernel scopes each call to the calling tenant + instance
and records cost + audit events.

| Property        | Milestone | Purpose |
|-----------------|-----------|---------|
| `Log`           | M5        | Structured logs back to the kernel (fire-and-forget). |
| `Llm`           | M5 (stub) | Provider-agnostic LLM completion — real adapters land with M10. |
| `State`         | M7a       | Durable KV per agent instance. |
| `Vector`        | M7a       | pgvector-backed RAG. Namespaces: `agent:{uuid}` or `shared:{name}`. |
| `Credentials`   | M7a       | Tenant-scoped secret resolver. Never log the value. |
| `Cost`          | M7a       | Record non-LLM cost events. |
| `Tool`          | M7a       | Call platform-provided tools by name (`datetime_now`, `hash_sha256`, …). |
| `Agents`        | M7a       | Sync multi-agent invocation. Child workflows land with M11. |
| `Artifact`      | M7b       | Content-addressed blob store with per-upload provenance rows. |
| `Human`         | M7c       | Approvals with T0-T3 tier routing (T3 auto-approve, T0 auto-block). |
| `Rule`          | M7d       | Effective-dated policy engine. |

## Direct-run mode

If `KONSTERA_KERNEL_MCP_URL` is unset, log/cost calls become warn-and-continue
no-ops and every other service throws `InvalidOperationException` — so
your agent boots and serves `/invoke` even outside a kernel, and unit
tests can exercise the shape without spinning up infrastructure.

## Tests

```bash
dotnet test sdk/dotnet/tests/Konstera.Sdk.Tests/Konstera.Sdk.Tests.csproj
```

11 direct-run-mode tests cover every service's kernel-required contract.
The end-to-end acceptance test is `agents/hello-world-dotnet` —
if the SDK's public surface breaks, that project fails to compile.

## Versioning

- **0.1.0** — M7g. Full surface: 11 services matching sdk/python v0.5.0.
  Requires `net10.0` and `ModelContextProtocol` 2.2.x.
