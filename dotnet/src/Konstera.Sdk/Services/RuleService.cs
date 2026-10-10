using System.Text.Json;
using System.Text.Json.Serialization;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

public sealed record Rule(
    [property: JsonPropertyName("ruleId")]        string RuleId,
    [property: JsonPropertyName("ruleKey")]       string RuleKey,
    [property: JsonPropertyName("version")]       int Version,
    [property: JsonPropertyName("content")]       JsonElement Content,
    [property: JsonPropertyName("description")]   string? Description,
    [property: JsonPropertyName("effectiveFrom")] string EffectiveFrom,
    [property: JsonPropertyName("effectiveTo")]   string? EffectiveTo,
    [property: JsonPropertyName("proposedAt")]    string ProposedAt,
    [property: JsonPropertyName("proposedByActor")] string? ProposedByActor,
    [property: JsonPropertyName("approvedByActor")] string? ApprovedByActor);

public sealed record RuleSummary(
    [property: JsonPropertyName("ruleKey")]     string RuleKey,
    [property: JsonPropertyName("versionCount")] int VersionCount,
    [property: JsonPropertyName("activeVersion")] int ActiveVersion,
    [property: JsonPropertyName("description")]  string? Description);

/// <summary>
/// Versioned rule/policy engine. Rules are effective-dated — asking for
/// a rule at a given time returns the version active THEN. Enables
/// reproducible re-execution of past invocations against the policy that
/// applied when they ran. Never expose rules_propose/decide via MCP — admin-only.
///
/// M8: caller instance UUID injected on every call for tenant resolution.
/// </summary>
public sealed class RuleService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public RuleService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public async Task<Rule> GetAsync(
        string ruleKey, DateTimeOffset? atTime = null, CancellationToken ct = default)
    {
        var args = new Dictionary<string, object?>
        {
            ["callerInstanceId"] = _instanceId,
            ["ruleKey"] = ruleKey,
        };
        if (atTime is not null) args["atTime"] = atTime.Value.ToUniversalTime().ToString("O");
        var raw = await _mcp.CallToolForResultAsync("rule_get", args, ct);
        return JsonSerializer.Deserialize<Rule>(raw ?? "{}", Json.Options)!;
    }

    public async Task<Rule> GetByIdAsync(string ruleId, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "rule_get_by_id",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["ruleId"] = ruleId,
            },
            ct);
        return JsonSerializer.Deserialize<Rule>(raw ?? "{}", Json.Options)!;
    }

    public async Task<IReadOnlyList<RuleSummary>> ListAsync(CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "rule_list",
            new Dictionary<string, object?> { ["callerInstanceId"] = _instanceId },
            ct);
        if (string.IsNullOrEmpty(raw)) return Array.Empty<RuleSummary>();
        return JsonSerializer.Deserialize<RuleSummary[]>(raw, Json.Options) ?? Array.Empty<RuleSummary>();
    }
}
