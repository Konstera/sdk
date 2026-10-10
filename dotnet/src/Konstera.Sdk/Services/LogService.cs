using System.Text.Json;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// Structured logging back to the kernel via MCP. Fields (extra kwargs)
/// are JSON-serialised and passed to the kernel, which resolves the
/// caller's tenant, writes the row to <c>invocation_logs</c> (keyed by
/// the ambient invocation id from <see cref="InvocationContext"/>), and
/// mirrors to its own log sink.
///
/// Log calls are fire-and-forget — <c>KernelMcpClient.CallToolAsync</c>
/// swallows exceptions, so business logic won't break because a log line
/// failed. When no invocation is in scope (e.g. logs from
/// <c>InitializeAsync</c>) the kernel-side DB write is skipped but the
/// mirror log still fires.
/// </summary>
public sealed class LogService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public LogService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public Task InfoAsync(string message, object? fields = null, CancellationToken ct = default) =>
        _mcp.CallToolAsync("log_info",  Payload(message, fields), ct);

    public Task WarnAsync(string message, object? fields = null, CancellationToken ct = default) =>
        _mcp.CallToolAsync("log_warn",  Payload(message, fields), ct);

    public Task ErrorAsync(string message, object? fields = null, CancellationToken ct = default) =>
        _mcp.CallToolAsync("log_error", Payload(message, fields), ct);

    private Dictionary<string, object?> Payload(string message, object? fields)
    {
        var args = new Dictionary<string, object?>
        {
            ["callerInstanceId"] = _instanceId,
            ["message"]          = message,
            ["fields"]           = fields is null ? "{}" : JsonSerializer.Serialize(fields, Json.Options),
        };
        var invocationId = InvocationContext.Current;
        if (!string.IsNullOrEmpty(invocationId))
        {
            args["invocationId"] = invocationId;
        }
        return args;
    }
}
