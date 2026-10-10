using System.Text.Json;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// Call platform-provided tools by name. Discover with <see cref="ListAsync"/>.
/// M7a built-ins: datetime_now, datetime_parse, hash_sha256, uuid_new,
/// json_validate.
/// </summary>
public sealed class ToolService
{
    private readonly KernelMcpClient _mcp;
    public ToolService(KernelMcpClient mcp) => _mcp = mcp;

    public async Task<IReadOnlyList<JsonElement>> ListAsync(CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync("tool_list", new Dictionary<string, object?>(), ct);
        if (string.IsNullOrEmpty(raw)) return Array.Empty<JsonElement>();
        return JsonSerializer.Deserialize<JsonElement[]>(raw, Json.Options) ?? Array.Empty<JsonElement>();
    }

    public async Task<JsonElement> CallAsync(string name, object? args = null, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "tool_call",
            new Dictionary<string, object?>
            {
                ["name"] = name,
                ["argsJson"] = args is null ? "{}" : JsonSerializer.Serialize(args, Json.Options),
            },
            ct);
        if (string.IsNullOrEmpty(raw)) return default;
        using var doc = JsonDocument.Parse(raw);
        return doc.RootElement.Clone();
    }
}
