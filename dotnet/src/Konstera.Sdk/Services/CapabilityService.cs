using System.Text.Json;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// ADR-013 purpose-first indirection over connectors.
///
/// Agents call canonical capability names (<c>orders.lookup_by_email</c>,
/// <c>tickets.reply</c>) without knowing which connector backs them. The
/// operator binds each capability to a connection at install time.
///
/// Mirror of <c>konstera_sdk.capability.CapabilityService</c>.
///
/// Example:
/// <code>
/// if (await ctx.Capability.AvailableAsync("orders.lookup_by_email", ct))
/// {
///     var order = await ctx.Capability.CallAsync&lt;Order&gt;(
///         "orders.lookup_by_email",
///         new Dictionary&lt;string, object?&gt; { ["email"] = email },
///         ct);
/// }
/// </code>
/// </summary>
public sealed class CapabilityService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public CapabilityService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    /// <summary>
    /// Check whether a capability is bound for this agent instance.
    /// Cheap single DB hit. Returns false on malformed responses (fails closed).
    /// </summary>
    public async Task<bool> AvailableAsync(string name, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "capability_available",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["name"] = name,
            },
            ct);
        if (string.IsNullOrEmpty(raw)) return false;
        try
        {
            using var doc = JsonDocument.Parse(raw);
            return doc.RootElement.TryGetProperty("available", out var p) && p.GetBoolean();
        }
        catch (JsonException)
        {
            return false;
        }
    }

    /// <summary>
    /// Invoke a capability by canonical name.
    /// </summary>
    /// <param name="name">Canonical capability name from the catalogue.</param>
    /// <param name="args">Capability-specific keyword arguments.</param>
    /// <returns>Decoded JSON result (JsonElement), or null for empty response.</returns>
    /// <exception cref="CapabilityUnbound">No binding for this capability on this instance.</exception>
    /// <exception cref="CapabilityUpstreamFailed">The connector or recipe backing this capability failed.</exception>
    /// <exception cref="CapabilityError">Other capability-layer failure.</exception>
    public async Task<JsonElement?> CallAsync(
        string name,
        IDictionary<string, object?>? args = null,
        CancellationToken ct = default)
    {
        var argsJson = JsonSerializer.Serialize(args ?? new Dictionary<string, object?>(), Json.Options);
        var payload = new Dictionary<string, object?>
        {
            ["callerInstanceId"] = _instanceId,
            ["name"] = name,
            ["argsJson"] = argsJson,
        };
        var invocationId = InvocationContext.Current;
        if (invocationId is not null) payload["invocationId"] = invocationId;

        string? raw;
        try
        {
            raw = await _mcp.CallToolForResultAsync("capability_call", payload, ct);
        }
        catch (Exception e)
        {
            // Direct-run (no kernel URL) raises InvalidOperationException with
            // a "KONSTERA_KERNEL_MCP_URL is unset" message — don't wrap it
            // into a capability-layer error. Let it propagate so the real
            // cause (missing kernel) surfaces to the caller.
            if (e is InvalidOperationException && e.Message.Contains("KONSTERA_KERNEL_MCP_URL"))
                throw;

            // Kernel surfaces real CapabilityError sub-codes via "[Code] ..." prefix.
            var msg = e.Message ?? string.Empty;
            if (msg.Contains("[Unbound]")) throw new CapabilityUnbound(msg, e);
            if (msg.Contains("[UpstreamFailed]") || msg.Contains("[ResponseShapeInvalid]"))
                throw new CapabilityUpstreamFailed(msg, e);
            throw new CapabilityError(msg, e);
        }

        if (string.IsNullOrEmpty(raw)) return null;
        try
        {
            using var doc = JsonDocument.Parse(raw);
            return doc.RootElement.Clone();
        }
        catch (JsonException)
        {
            // Legacy recipes may return a plain string.
            return JsonSerializer.SerializeToElement(raw, Json.Options);
        }
    }

    /// <summary>
    /// Typed variant — deserialises the response into <typeparamref name="T"/>.
    /// Returns default when the response is empty or doesn't match the shape.
    /// </summary>
    public async Task<T?> CallAsync<T>(
        string name,
        IDictionary<string, object?>? args = null,
        CancellationToken ct = default)
    {
        var element = await CallAsync(name, args, ct);
        if (element is null) return default;
        try
        {
            return element.Value.Deserialize<T>(Json.Options);
        }
        catch (JsonException)
        {
            return default;
        }
    }
}

/// <summary>Base for all capability-layer errors.</summary>
public class CapabilityError : InvalidOperationException
{
    public CapabilityError(string message, Exception? inner = null) : base(message, inner) { }
}

/// <summary>The agent has no binding for this capability in the current install.</summary>
public sealed class CapabilityUnbound : CapabilityError
{
    public CapabilityUnbound(string message, Exception? inner = null) : base(message, inner) { }
}

/// <summary>The connector or REST recipe backing this capability threw.</summary>
public sealed class CapabilityUpstreamFailed : CapabilityError
{
    public CapabilityUpstreamFailed(string message, Exception? inner = null) : base(message, inner) { }
}
