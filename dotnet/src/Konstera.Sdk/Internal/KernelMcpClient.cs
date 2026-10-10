using System.Text.Json;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using ModelContextProtocol.Client;

namespace Konstera.Sdk.Internal;

/// <summary>
/// Internal wrapper around the MCP client. Session-per-process pattern:
/// created once at Run() startup, reused across the agent's whole
/// lifetime. If the URL is unset (direct-run mode), all tool calls
/// degrade gracefully — CallToolAsync becomes a warn-and-continue no-op
/// and CallToolForResultAsync throws so agents can guard for the case.
///
/// Mirrors <c>konstera_sdk._mcp.KernelMcpClient</c> in the Python SDK.
/// </summary>
public sealed class KernelMcpClient : IAsyncDisposable
{
    private readonly string? _url;
    private readonly ILogger _log;
    private McpClient? _client;
    private readonly SemaphoreSlim _connectLock = new(1, 1);

    public KernelMcpClient(string? url, ILogger? logger = null)
    {
        _url = url;
        _log = logger ?? NullLogger.Instance;
    }

    public bool Enabled => !string.IsNullOrWhiteSpace(_url);

    /// <summary>
    /// Fire-and-forget tool call. Logs on failure but does NOT rethrow —
    /// used for observability calls (log_*, cost_record) where the agent's
    /// business logic must not break because a log line failed.
    /// </summary>
    public async Task CallToolAsync(
        string name,
        IReadOnlyDictionary<string, object?> args,
        CancellationToken ct = default)
    {
        if (!Enabled)
        {
            _log.LogDebug("MCP disabled; skipping {Tool}", name);
            return;
        }
        try
        {
            var client = await GetOrConnectAsync(ct);
            await client.CallToolAsync(name, args, cancellationToken: ct);
        }
        catch (Exception ex)
        {
            _log.LogWarning(ex, "MCP tool call failed: {Tool}", name);
        }
    }

    /// <summary>
    /// Tool call that returns the tool's result as a string. Rethrows on
    /// failure — used for calls where the agent semantically needs the
    /// response (state.get, credentials.get, rule.get, artifact.get, etc.).
    /// </summary>
    public async Task<string?> CallToolForResultAsync(
        string name,
        IReadOnlyDictionary<string, object?> args,
        CancellationToken ct = default)
    {
        if (!Enabled)
        {
            throw new InvalidOperationException(
                $"Cannot call MCP tool '{name}' — KONSTERA_KERNEL_MCP_URL is unset. " +
                $"This is expected in direct-run mode; the agent should guard against it " +
                $"or run inside an Konstera kernel.");
        }

        var client = await GetOrConnectAsync(ct);
        var result = await client.CallToolAsync(name, args, cancellationToken: ct);
        if (result.Content is null || result.Content.Count == 0)
        {
            return null;
        }
        // For string-returning tools the kernel puts the value in one
        // TextContentBlock; join text parts defensively in case future
        // servers split them.
        var texts = new List<string>();
        foreach (var block in result.Content)
        {
            var text = block.GetType().GetProperty("Text")?.GetValue(block) as string;
            if (text is not null) texts.Add(text);
        }
        return texts.Count == 0 ? null : string.Concat(texts);
    }

    private async Task<McpClient> GetOrConnectAsync(CancellationToken ct)
    {
        if (_client is not null) return _client;
        await _connectLock.WaitAsync(ct);
        try
        {
            if (_client is not null) return _client;
            var transport = new HttpClientTransport(new HttpClientTransportOptions
            {
                Endpoint = new Uri(_url!),
                Name = "konstera-sdk-dotnet",
            });
            _client = await McpClient.CreateAsync(transport, cancellationToken: ct);
            _log.LogInformation("Connected to Konstera kernel MCP at {Url}", _url);
            return _client;
        }
        finally
        {
            _connectLock.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_client is IAsyncDisposable ad) await ad.DisposeAsync();
        else if (_client is IDisposable d) d.Dispose();
        _connectLock.Dispose();
    }
}

// Shared JSON options — matches the wire format the kernel expects.
internal static class Json
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull,
    };
}
