namespace Konstera.Sdk;

/// <summary>
/// Base class every Konstera .NET agent extends. Override <see cref="HandleAsync"/>
/// (required); optionally override <see cref="InitializeAsync"/> for one-time
/// setup and <see cref="ShutdownAsync"/> for cleanup.
///
/// The SDK's <see cref="AgentRuntime.RunAsync"/> wires this up to an HTTP
/// server + MCP client, but the class itself has no coupling to the transport
/// — this makes agents unit-testable without spinning up any infrastructure.
///
/// Mirrors <c>konstera_sdk.Agent</c> in the Python SDK.
/// </summary>
public abstract class Agent
{
    /// <summary>
    /// Called once at container startup. Load models, warm caches, open
    /// long-lived connections here. Default: no-op.
    /// </summary>
    public virtual Task InitializeAsync(AgentContext ctx, CancellationToken ct) => Task.CompletedTask;

    /// <summary>
    /// Called for every invocation. Must be overridden.
    /// </summary>
    public abstract Task<AgentResponse> HandleAsync(AgentRequest req, AgentContext ctx, CancellationToken ct);

    /// <summary>
    /// Called on graceful stop. Close connections, flush buffers here.
    /// Default: no-op.
    /// </summary>
    public virtual Task ShutdownAsync(AgentContext ctx, CancellationToken ct) => Task.CompletedTask;
}
