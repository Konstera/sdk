using System.Text.Json;
using System.Text.Json.Serialization;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

public sealed record VectorHit(
    [property: JsonPropertyName("id")]         string Id,
    [property: JsonPropertyName("externalId")] string? ExternalId,
    [property: JsonPropertyName("content")]    string Content,
    [property: JsonPropertyName("metadata")]   JsonElement? Metadata,
    [property: JsonPropertyName("score")]      double Score);

/// <summary>
/// pgvector-backed RAG store. Namespaces: <c>agent:{instance-uuid}</c>
/// (private) or <c>shared:{name}</c> (tenant-wide). Kernel currently uses
/// a stub embedder; real embeddings arrive with M10.
///
/// M8: caller instance UUID injected on every call for tenant resolution.
/// </summary>
public sealed class VectorService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public VectorService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public async Task<string> UpsertAsync(
        string @namespace,
        string content,
        string? externalId = null,
        object? metadata = null,
        CancellationToken ct = default)
    {
        var args = new Dictionary<string, object?>
        {
            ["callerInstanceId"] = _instanceId,
            ["namespace"] = @namespace,
            ["content"]   = content,
        };
        if (externalId is not null) args["externalId"] = externalId;
        if (metadata is not null)   args["metadataJson"] = JsonSerializer.Serialize(metadata, Json.Options);

        var raw = await _mcp.CallToolForResultAsync("vector_upsert", args, ct);
        if (string.IsNullOrEmpty(raw)) return "";
        using var doc = JsonDocument.Parse(raw);
        return doc.RootElement.TryGetProperty("chunkId", out var cid) ? cid.GetString() ?? "" : raw;
    }

    public async Task<IReadOnlyList<VectorHit>> QueryAsync(
        string @namespace,
        string queryText,
        int topK = 5,
        CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "vector_query",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["namespace"] = @namespace,
                ["queryText"] = queryText,
                ["topK"] = topK,
            },
            ct);
        if (string.IsNullOrEmpty(raw)) return Array.Empty<VectorHit>();
        return JsonSerializer.Deserialize<VectorHit[]>(raw, Json.Options) ?? Array.Empty<VectorHit>();
    }

    public Task DeleteAsync(string @namespace, string externalId, CancellationToken ct = default) =>
        _mcp.CallToolForResultAsync(
            "vector_delete",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["namespace"] = @namespace,
                ["externalId"] = externalId,
            },
            ct);
}
