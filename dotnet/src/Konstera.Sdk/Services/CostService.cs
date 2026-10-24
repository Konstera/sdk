using System.Text.Json;
using System.Text.Json.Serialization;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// Record non-LLM cost events + read rolling spend summaries. LLM costs flow
/// through <see cref="LlmService"/> automatically; use <see cref="RecordAsync"/>
/// for external APIs, GPU rentals, reranker calls, etc. Use
/// <see cref="SummaryAsync"/> to self-govern against a budget without
/// maintaining your own counters.
/// </summary>
public sealed class CostService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public CostService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public Task RecordAsync(
        string kind,
        double costUsd,
        string? model = null,
        string? invocationId = null,
        int? inputTokens = null,
        int? outputTokens = null,
        int? cachedInputTokens = null,
        object? metadata = null,
        CancellationToken ct = default)
    {
        var args = new Dictionary<string, object?>
        {
            ["instanceId"] = _instanceId,
            ["kind"] = kind,
            ["costUsd"] = costUsd,
        };
        if (invocationId is not null)       args["invocationId"]       = invocationId;
        if (model is not null)              args["modelId"]            = model;
        if (inputTokens is not null)        args["inputTokens"]        = inputTokens;
        if (outputTokens is not null)       args["outputTokens"]       = outputTokens;
        if (cachedInputTokens is not null)  args["cachedInputTokens"]  = cachedInputTokens;
        if (metadata is not null)           args["metadataJson"]       = JsonSerializer.Serialize(metadata, Json.Options);
        return _mcp.CallToolForResultAsync("cost_record", args, ct);
    }

    /// <summary>
    /// Fetch this agent instance's rolling cost over the past N hours. Useful
    /// for self-governing agents that cap spend without maintaining their own
    /// counters. Returns null if the window is empty or the kernel doesn't yet
    /// expose the <c>cost_summary</c> MCP tool.
    /// </summary>
    /// <param name="windowHours">Lookback window in hours. Must be >= 1.</param>
    public async Task<CostSummary?> SummaryAsync(int windowHours = 24, CancellationToken ct = default)
    {
        if (windowHours < 1)
            throw new ArgumentOutOfRangeException(nameof(windowHours), "must be >= 1");

        var raw = await _mcp.CallToolForResultAsync(
            "cost_summary",
            new Dictionary<string, object?>
            {
                ["instanceId"] = _instanceId,
                ["windowHours"] = windowHours,
            },
            ct);

        if (string.IsNullOrEmpty(raw) || raw == "null") return null;
        try
        {
            return JsonSerializer.Deserialize<CostSummary>(raw, Json.Options);
        }
        catch (JsonException)
        {
            return null;
        }
    }
}

/// <summary>Rolling cost summary across a time window for this instance.</summary>
public sealed record CostSummary(
    [property: JsonPropertyName("window_hours")] int WindowHours,
    [property: JsonPropertyName("since")] string Since,
    [property: JsonPropertyName("until")] string Until,
    [property: JsonPropertyName("total_usd")] double TotalUsd,
    [property: JsonPropertyName("by_kind")] IReadOnlyDictionary<string, double> ByKind);
