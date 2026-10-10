using System.Text.Json;
using Konstera.Sdk.Internal;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Konstera.Sdk;

/// <summary>
/// SDK entry point. Hosts an <see cref="Agent"/> as a minimal HTTP server
/// exposing <c>/health</c>, <c>/describe</c>, <c>/invoke</c> — the exact
/// three routes ContainerAgentHost expects. Blocks until SIGTERM/SIGINT.
///
/// Mirrors <c>konstera_sdk.runtime.run</c>.
/// </summary>
public static class AgentRuntime
{
    /// <summary>Convenience sync wrapper matching the Python <c>run()</c> shape.</summary>
    public static void Run(Agent agent, int port = 8080)
        => RunAsync(agent, port).GetAwaiter().GetResult();

    public static async Task RunAsync(Agent agent, int port = 8080, CancellationToken ct = default)
    {
        var builder = WebApplication.CreateBuilder();
        // Silence Kestrel's default request logs — the kernel's invocation
        // record is the audit trail; per-request access logs would double-count.
        builder.Logging.AddFilter("Microsoft.AspNetCore.Hosting.Diagnostics", LogLevel.Warning);
        builder.WebHost.ConfigureKestrel(o => o.ListenAnyIP(port));

        var app = builder.Build();
        var logger = app.Logger;

        var mcpUrl = Environment.GetEnvironmentVariable("KONSTERA_KERNEL_MCP_URL");
        var mcp = new KernelMcpClient(mcpUrl, logger);
        var ctx = AgentContext.FromEnv(mcp);

        if (mcp.Enabled)
        {
            logger.LogInformation("Kernel MCP URL: {Url}", mcpUrl);
        }
        else
        {
            logger.LogWarning(
                "KONSTERA_KERNEL_MCP_URL not set — kernel callbacks disabled (direct-run mode).");
        }

        app.MapGet("/health", () => Results.Json(new
        {
            status = "ok", agent = ctx.AgentId, version = ctx.AgentVersion,
        }));

        app.MapGet("/describe", () => Results.Json(new
        {
            id = ctx.AgentId,
            version = ctx.AgentVersion,
            capabilities = new[] { "kernel-mcp-callback" },
            tools = Array.Empty<object>(),
        }));

        app.MapPost("/invoke", async (HttpContext http) =>
        {
            using var doc = await JsonDocument.ParseAsync(http.Request.Body, cancellationToken: http.RequestAborted);
            var root = doc.RootElement;
            var req = new AgentRequest(
                InvocationId: root.TryGetProperty("invocationId", out var id) ? id.GetString() ?? "missing" : "missing",
                Input:        root.TryGetProperty("input",        out var inp) ? inp.GetString() ?? ""   : "",
                Payload:      root.TryGetProperty("payload",      out var pl)  ? pl.Clone() : null);

            try
            {
                // Enter the ambient invocation scope so ctx.Log.* and
                // ctx.Llm.* auto-inject invocationId without the agent
                // having to thread it manually.
                using var _inv = InvocationContext.Enter(req.InvocationId);
                var resp = await agent.HandleAsync(req, ctx, http.RequestAborted);
                return Results.Json(new
                {
                    content = resp.Content,
                    structured = resp.Structured,
                    toolCalls = resp.ToolCalls,
                });
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "agent.HandleAsync failed for invocation {Id}", req.InvocationId);
                return Results.Json(new
                {
                    error = new { type = ex.GetType().Name, message = ex.Message },
                }, statusCode: 500);
            }
        });

        await agent.InitializeAsync(ctx, ct);
        try
        {
            await app.RunAsync(ct);
        }
        finally
        {
            try { await agent.ShutdownAsync(ctx, CancellationToken.None); }
            catch (Exception ex) { logger.LogWarning(ex, "agent.ShutdownAsync failed"); }
            await mcp.DisposeAsync();
        }
    }
}
