using System.Text.Json;
using System.Text.Json.Serialization;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

public sealed record HumanDecision(
    [property: JsonPropertyName("approvalId")]           string ApprovalId,
    [property: JsonPropertyName("kind")]                 string Kind,
    [property: JsonPropertyName("tier")]                 string Tier,
    [property: JsonPropertyName("status")]               string Status,
    [property: JsonPropertyName("summary")]              string Summary,
    [property: JsonPropertyName("submitterInstanceId")]  string SubmitterInstanceId,
    [property: JsonPropertyName("submitterActor")]       string? SubmitterActor,
    [property: JsonPropertyName("submitterRole")]        string? SubmitterRole,
    [property: JsonPropertyName("invocationId")]         string? InvocationId,
    [property: JsonPropertyName("options")]              IReadOnlyList<string> Options,
    [property: JsonPropertyName("decision")]             string? Decision,
    [property: JsonPropertyName("deciderActor")]         string? DeciderActor,
    [property: JsonPropertyName("deciderRole")]          string? DeciderRole,
    [property: JsonPropertyName("decisionReason")]       string? DecisionReason,
    [property: JsonPropertyName("submittedAt")]          string SubmittedAt,
    [property: JsonPropertyName("decidedAt")]            string? DecidedAt,
    [property: JsonPropertyName("detail")]               JsonElement? Detail)
{
    public bool IsResolved => Status is "approved" or "rejected" or "expired";
    public bool IsApproved => Status == "approved";
}

public sealed record HumanRequestOptions(
    string Kind,
    string Tier,
    string Summary,
    object? Detail = null,
    string? SubmitterRole = null,
    string? InvocationId = null,
    IReadOnlyList<string>? Options = null,
    int? WaitSeconds = null);

/// <summary>
/// Human approval service. Tier semantics (T0-T3) mirror finance-req doc
/// Table 18: T3 auto-approves, T2 auto-approves w/ retro-review, T0 blocks,
/// T1 waits for human. Never expose `human_decide` from an agent — that's
/// admin-only via HTTP.
/// </summary>
public sealed class HumanService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public HumanService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public async Task<HumanDecision> RequestAsync(HumanRequestOptions opts, CancellationToken ct = default)
    {
        var args = new Dictionary<string, object?>
        {
            ["instanceId"] = _instanceId,
            ["kind"]       = opts.Kind,
            ["tier"]       = opts.Tier,
            ["summary"]    = opts.Summary,
        };
        if (opts.Detail is not null)        args["detailJson"]    = JsonSerializer.Serialize(opts.Detail, Json.Options);
        if (opts.Options is not null)       args["optionsJson"]   = JsonSerializer.Serialize(opts.Options, Json.Options);
        if (opts.SubmitterRole is not null) args["submitterRole"] = opts.SubmitterRole;
        if (opts.InvocationId is not null)  args["invocationId"]  = opts.InvocationId;

        var raw = await _mcp.CallToolForResultAsync("human_submit", args, ct);
        var decision = JsonSerializer.Deserialize<HumanDecision>(raw ?? "{}", Json.Options)!;

        // Client-side wait — only useful for T1. T0/T2/T3 already resolved.
        if (opts.WaitSeconds is { } ws and > 0 && decision.Status == "pending")
        {
            decision = await WaitAsync(decision.ApprovalId, ws, ct);
        }
        return decision;
    }

    public async Task<HumanDecision> GetAsync(string approvalId, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "human_get",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["approvalId"] = approvalId,
            },
            ct);
        return JsonSerializer.Deserialize<HumanDecision>(raw ?? "{}", Json.Options)!;
    }

    public async Task<HumanDecision> WaitAsync(
        string approvalId, int timeoutSeconds = 30, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "human_wait",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["approvalId"]       = approvalId,
                ["timeoutSeconds"]   = timeoutSeconds,
            },
            ct);
        return JsonSerializer.Deserialize<HumanDecision>(raw ?? "{}", Json.Options)!;
    }

    public async Task<IReadOnlyList<HumanDecision>> ListPendingAsync(
        bool mineOnly = false, int limit = 50, CancellationToken ct = default)
    {
        var args = new Dictionary<string, object?>
        {
            ["callerInstanceId"] = _instanceId,
            ["limit"] = limit,
        };
        if (mineOnly) args["submitterInstanceId"] = _instanceId;
        var raw = await _mcp.CallToolForResultAsync("human_list_pending", args, ct);
        if (string.IsNullOrEmpty(raw)) return Array.Empty<HumanDecision>();
        return JsonSerializer.Deserialize<HumanDecision[]>(raw, Json.Options) ?? Array.Empty<HumanDecision>();
    }
}
