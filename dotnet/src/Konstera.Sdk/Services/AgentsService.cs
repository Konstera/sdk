using System.Text.Json;
using System.Text.Json.Serialization;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

public sealed record AgentInvokeResult(
    [property: JsonPropertyName("targetInstanceId")] string TargetInstanceId,
    [property: JsonPropertyName("invocationId")]     string InvocationId,
    [property: JsonPropertyName("response")]         JsonElement Response);

/// <summary>
/// Multi-agent synchronous invocation. Target must already be loaded on
/// the kernel — this deliberately does NOT spawn on-demand. Temporal child
/// workflows land with M11.
///
/// M8: kernel enforces same-tenant callee. Caller instance UUID is injected
/// automatically so the kernel can resolve caller-tenant and verify the
/// callee belongs to the same tenant.
/// </summary>
public sealed class AgentsService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public AgentsService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public async Task<AgentInvokeResult> InvokeAsync(
        string targetInstanceId,
        string input,
        object? payload = null,
        int? timeoutSeconds = null,
        CancellationToken ct = default)
    {
        var args = new Dictionary<string, object?>
        {
            ["callerInstanceId"] = _instanceId,
            ["targetInstanceId"] = targetInstanceId,
            ["input"] = input,
        };
        if (payload is not null)        args["payloadJson"]    = JsonSerializer.Serialize(payload, Json.Options);
        if (timeoutSeconds is not null) args["timeoutSeconds"] = timeoutSeconds;

        var raw = await _mcp.CallToolForResultAsync("agents_invoke", args, ct);
        if (string.IsNullOrEmpty(raw))
        {
            throw new InvalidOperationException("agents_invoke returned empty result.");
        }
        return JsonSerializer.Deserialize<AgentInvokeResult>(raw, Json.Options)
            ?? throw new InvalidOperationException("agents_invoke returned malformed JSON.");
    }
}
