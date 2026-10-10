using System.Text.Json;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// Record non-LLM cost events. LLM costs will flow through <see cref="LlmService"/>
/// automatically once M10's real adapters land.
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
}
