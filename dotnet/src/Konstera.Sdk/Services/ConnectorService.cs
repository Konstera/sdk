using System.Text.Json;
using System.Text.Json.Serialization;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// One entry from <see cref="ConnectorService.ListAsync"/> — the agent's
/// granted connections. `alias` is what you pass to CallAsync.
/// </summary>
public sealed record ConnectorGrant(
    [property: JsonPropertyName("alias")]            string Alias,
    [property: JsonPropertyName("connectorTypeKey")] string ConnectorTypeKey,
    [property: JsonPropertyName("connectionId")]     string ConnectionId,
    [property: JsonPropertyName("scope")]            JsonElement Scope);

/// <summary>
/// Agent-facing view of the connector framework (ADR-009). Two operations:
///   - ListAsync — what am I granted?
///   - CallAsync — invoke a granted connection
///
/// Zero connection setup on the agent side — the tenant configures the
/// connection once in the portal, an admin grants this agent access, and
/// the agent calls by alias.
///
/// Fluent-style handles (ctx.Connector("shopify_uk").Call(...)) are added
/// as a v2 sugar; for now the surface is deliberately narrow.
/// </summary>
public sealed class ConnectorService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public ConnectorService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    /// <summary>The connections this agent has been granted.</summary>
    public async Task<IReadOnlyList<ConnectorGrant>> ListAsync(CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "connector_list",
            new Dictionary<string, object?> { ["callerInstanceId"] = _instanceId },
            ct);
        if (string.IsNullOrEmpty(raw)) return Array.Empty<ConnectorGrant>();
        return JsonSerializer.Deserialize<ConnectorGrant[]>(raw, Json.Options)
               ?? Array.Empty<ConnectorGrant>();
    }

    /// <summary>
    /// Invoke a granted connection. `alias` is what the tenant named it
    /// (e.g. "shopify_uk", "pg_analytics"). `method` is connector-type-specific
    /// (postgres: "query"/"list_tables"/"describe_table"; commercetools:
    /// "products.query"/"orders.list"; etc). `args` is a JSON object.
    ///
    /// Returns the raw JSON response as a <see cref="JsonElement"/>; the
    /// caller casts to whatever shape the specific method returns.
    /// </summary>
    public async Task<JsonElement> CallAsync(
        string alias, string method, object? args = null, CancellationToken ct = default)
    {
        var argsJson = args is null ? "{}" : JsonSerializer.Serialize(args, Json.Options);
        var raw = await _mcp.CallToolForResultAsync(
            "connector_call",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["alias"] = alias,
                ["method"] = method,
                ["argsJson"] = argsJson,
            },
            ct);
        if (string.IsNullOrEmpty(raw)) return JsonDocument.Parse("{}").RootElement;
        return JsonDocument.Parse(raw).RootElement;
    }
}
