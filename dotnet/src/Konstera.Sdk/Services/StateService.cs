using System.Text.Json;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// Durable KV per agent instance, scoped by tenant. Values are JSON —
/// dicts, lists, strings, numbers, booleans, null all work.
/// </summary>
public sealed class StateService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public StateService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public async Task<JsonElement?> GetAsync(string key, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "state_get",
            new Dictionary<string, object?> { ["instanceId"] = _instanceId, ["key"] = key },
            ct);
        if (string.IsNullOrEmpty(raw) || raw == "null") return null;
        using var doc = JsonDocument.Parse(raw);
        return doc.RootElement.Clone();
    }

    public Task SetAsync(string key, object? value, CancellationToken ct = default) =>
        _mcp.CallToolForResultAsync(
            "state_set",
            new Dictionary<string, object?>
            {
                ["instanceId"] = _instanceId,
                ["key"] = key,
                ["valueJson"] = JsonSerializer.Serialize(value, Json.Options),
            },
            ct);

    public Task DeleteAsync(string key, CancellationToken ct = default) =>
        _mcp.CallToolForResultAsync(
            "state_delete",
            new Dictionary<string, object?> { ["instanceId"] = _instanceId, ["key"] = key },
            ct);

    public async Task<IReadOnlyList<string>> ListAsync(string prefix = "", CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "state_list",
            new Dictionary<string, object?> { ["instanceId"] = _instanceId, ["prefix"] = prefix },
            ct);
        if (string.IsNullOrEmpty(raw)) return Array.Empty<string>();
        return JsonSerializer.Deserialize<string[]>(raw, Json.Options) ?? Array.Empty<string>();
    }
}
