using System.Text.Json;
using System.Text.Json.Serialization;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

public sealed record ArtifactPutResult(
    [property: JsonPropertyName("artifactId")]  string ArtifactId,
    [property: JsonPropertyName("sha256")]      string Sha256,
    [property: JsonPropertyName("sizeBytes")]   long SizeBytes,
    [property: JsonPropertyName("contentType")] string ContentType,
    [property: JsonPropertyName("storageUri")]  string StorageUri,
    [property: JsonPropertyName("dedup")]       bool Dedup);

public sealed record ArtifactGetResult(byte[] Content, string ContentType, long SizeBytes, string Sha256);

public sealed record ArtifactHeadResult(bool Exists, string Sha256, long? SizeBytes, string? ContentType);

public sealed record ArtifactListItem(
    [property: JsonPropertyName("artifactId")]   string ArtifactId,
    [property: JsonPropertyName("sha256")]       string Sha256,
    [property: JsonPropertyName("sizeBytes")]    long SizeBytes,
    [property: JsonPropertyName("contentType")]  string ContentType,
    [property: JsonPropertyName("invocationId")] string? InvocationId,
    [property: JsonPropertyName("uploadedAt")]   string UploadedAt,
    [property: JsonPropertyName("metadata")]     JsonElement? Metadata);

/// <summary>
/// Content-addressed blob store with provenance trail. Same content
/// uploaded twice by the same tenant → same sha256 → one physical blob
/// but N metadata rows for audit.
/// </summary>
public sealed class ArtifactService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public ArtifactService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public async Task<ArtifactPutResult> PutAsync(
        byte[] content,
        string contentType,
        string? invocationId = null,
        object? metadata = null,
        CancellationToken ct = default)
    {
        var args = new Dictionary<string, object?>
        {
            ["instanceId"]    = _instanceId,
            ["contentBase64"] = Convert.ToBase64String(content),
            ["contentType"]   = contentType,
        };
        if (invocationId is not null) args["invocationId"] = invocationId;
        if (metadata is not null)     args["metadataJson"] = JsonSerializer.Serialize(metadata, Json.Options);

        var raw = await _mcp.CallToolForResultAsync("artifact_put", args, ct);
        return JsonSerializer.Deserialize<ArtifactPutResult>(raw ?? "{}", Json.Options)!;
    }

    public async Task<ArtifactGetResult> GetAsync(string sha256, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "artifact_get",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["sha256"] = sha256,
            },
            ct);
        using var doc = JsonDocument.Parse(raw!);
        var root = doc.RootElement;
        return new ArtifactGetResult(
            Content:     Convert.FromBase64String(root.GetProperty("contentBase64").GetString()!),
            ContentType: root.GetProperty("contentType").GetString() ?? "application/octet-stream",
            SizeBytes:   root.GetProperty("sizeBytes").GetInt64(),
            Sha256:      root.GetProperty("sha256").GetString() ?? sha256);
    }

    public async Task<ArtifactHeadResult> HeadAsync(string sha256, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "artifact_head",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["sha256"] = sha256,
            },
            ct);
        using var doc = JsonDocument.Parse(raw!);
        var root = doc.RootElement;
        var exists = root.GetProperty("exists").GetBoolean();
        return new ArtifactHeadResult(
            Exists:      exists,
            Sha256:      root.GetProperty("sha256").GetString() ?? sha256,
            SizeBytes:   exists && root.TryGetProperty("sizeBytes",   out var sb) ? sb.GetInt64()  : null,
            ContentType: exists && root.TryGetProperty("contentType", out var ct2) ? ct2.GetString() : null);
    }

    public async Task<IReadOnlyList<ArtifactListItem>> ListByUploaderAsync(
        string? uploaderInstanceId = null,
        int limit = 50,
        CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "artifact_list_by_uploader",
            new Dictionary<string, object?>
            {
                ["uploaderInstanceId"] = uploaderInstanceId ?? _instanceId,
                ["limit"] = limit,
            },
            ct);
        if (string.IsNullOrEmpty(raw)) return Array.Empty<ArtifactListItem>();
        return JsonSerializer.Deserialize<ArtifactListItem[]>(raw, Json.Options) ?? Array.Empty<ArtifactListItem>();
    }
}
