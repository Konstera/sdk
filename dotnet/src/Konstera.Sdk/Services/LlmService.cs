using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// Wrapper around the kernel MCP <c>llm_complete</c> tool.
///
/// Two calling shapes (ADR-011 §2):
///   1. <c>CompleteAsync(prompt, purpose: "narrator", …)</c> — RECOMMENDED.
///      Kernel resolves the tenant's binding for this purpose → concrete
///      model + credentials + budget cap. Rebinding is a portal action;
///      agent code doesn't change.
///   2. <c>CompleteAsync(prompt, model: "gpt-4o-mini", …)</c> — escape
///      hatch. Bypasses purpose indirection; kernel picks the provider
///      by model prefix.
///
/// Automatically injects <c>callerInstanceId</c> (ctor) + <c>invocationId</c>
/// (from <see cref="InvocationContext"/>) so <c>usage_events</c> rows carry
/// the FK.
/// </summary>
public sealed class LlmService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public LlmService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public async Task<string> CompleteAsync(
        string prompt,
        string? purpose = null,
        string? model = null,
        double? temperature = null,
        int? maxTokens = null,
        string? system = null,
        string? invocationId = null,
        CancellationToken ct = default)
    {
        if (string.IsNullOrEmpty(purpose) && string.IsNullOrEmpty(model))
        {
            throw new ArgumentException("Must supply either `purpose` or `model`.");
        }

        var args = new Dictionary<string, object?>
        {
            ["callerInstanceId"] = _instanceId,
            ["prompt"]           = prompt,
        };
        if (purpose is not null)     args["purpose"]     = purpose;
        if (model is not null)       args["model"]       = model;
        if (system is not null)      args["system"]      = system;
        if (temperature is not null) args["temperature"] = temperature;
        if (maxTokens is not null)   args["maxTokens"]   = maxTokens;

        // Explicit invocationId wins; otherwise auto-inject from ambient scope.
        var effectiveInv = invocationId ?? InvocationContext.Current;
        if (!string.IsNullOrEmpty(effectiveInv)) args["invocationId"] = effectiveInv;

        var result = await _mcp.CallToolForResultAsync("llm_complete", args, ct);
        return result ?? "";
    }
}
