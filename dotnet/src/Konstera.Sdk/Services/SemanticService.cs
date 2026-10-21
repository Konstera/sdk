using System.Text.Json;
using System.Text.Json.Serialization;
using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// Tenant semantic plane access (ADR-037). Agents read:
/// <list type="bullet">
///   <item>Glossary terms — business-term definitions</item>
///   <item>Ontology entities — business entities with identity strategies</item>
///   <item>Skills — named reusable playbooks</item>
///   <item>Eval signals — cluster-level pass rates from the harness</item>
/// </list>
///
/// All methods return null/empty for the ADR-039 feature-disabled envelope,
/// so agents branch on data availability rather than special-casing
/// feature-off tenants.
///
/// Mirror of <c>konstera_sdk.semantic.SemanticService</c>.
/// </summary>
public sealed class SemanticService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public SemanticService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    /// <summary>Look up a glossary term by name (case-insensitive, synonyms searched).</summary>
    public async Task<GlossaryTerm?> GlossaryLookupAsync(string term, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "context_glossary_lookup",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["term"] = term,
            },
            ct);
        if (string.IsNullOrEmpty(raw) || raw == "null") return null;
        var element = JsonDocument.Parse(raw).RootElement;
        if (IsFeatureDisabled(element)) return null;
        return element.Deserialize<GlossaryTerm>(Json.Options);
    }

    /// <summary>List active glossary terms, optionally filtered by domain.</summary>
    public async Task<IReadOnlyList<GlossaryTerm>> GlossaryListAsync(
        string? domain = null,
        CancellationToken ct = default)
    {
        var args = new Dictionary<string, object?> { ["callerInstanceId"] = _instanceId };
        if (domain is not null) args["domain"] = domain;

        var raw = await _mcp.CallToolForResultAsync("context_glossary_list", args, ct);
        if (string.IsNullOrEmpty(raw)) return Array.Empty<GlossaryTerm>();
        var element = JsonDocument.Parse(raw).RootElement;
        if (IsFeatureDisabled(element)) return Array.Empty<GlossaryTerm>();
        if (element.ValueKind != JsonValueKind.Array) return Array.Empty<GlossaryTerm>();
        return element.Deserialize<GlossaryTerm[]>(Json.Options) ?? Array.Empty<GlossaryTerm>();
    }

    /// <summary>
    /// Look up a business entity from the tenant ontology. For the <c>customer</c>
    /// entity under the thin-semantic model (migration 115), <c>Properties</c>
    /// carries <c>identity.primary</c> + <c>identity.fallbacks[]</c> + <c>key_attributes</c>.
    /// </summary>
    public async Task<OntologyEntity?> OntologyLookupAsync(string entityName, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "context_ontology_resolve",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["entityName"] = entityName,
            },
            ct);
        if (string.IsNullOrEmpty(raw) || raw == "null") return null;
        var element = JsonDocument.Parse(raw).RootElement;
        if (IsFeatureDisabled(element)) return null;
        return OntologyEntity.FromJson(element);
    }

    /// <summary>Fetch a skill with its ordered steps.</summary>
    public async Task<Skill?> SkillsGetAsync(string name, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "context_skills_get",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["skillName"] = name,
            },
            ct);
        if (string.IsNullOrEmpty(raw) || raw == "null") return null;
        var element = JsonDocument.Parse(raw).RootElement;
        if (IsFeatureDisabled(element)) return null;
        return element.Deserialize<Skill>(Json.Options);
    }

    /// <summary>
    /// Fetch per-cluster pass rates for an agent (ADR-037 M13 W3-B).
    /// Pass the agent <b>package</b> UUID, not the instance id.
    /// </summary>
    public async Task<IReadOnlyDictionary<string, ClusterPassRate>> ClusterPassRatesAsync(
        string agentId,
        CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "context_evaluation_cluster_pass_rates",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["agentId"] = agentId,
            },
            ct);
        if (string.IsNullOrEmpty(raw))
            return new Dictionary<string, ClusterPassRate>();
        var element = JsonDocument.Parse(raw).RootElement;
        if (IsFeatureDisabled(element))
            return new Dictionary<string, ClusterPassRate>();
        if (element.ValueKind != JsonValueKind.Object)
            return new Dictionary<string, ClusterPassRate>();
        return element.Deserialize<Dictionary<string, ClusterPassRate>>(Json.Options)
            ?? new Dictionary<string, ClusterPassRate>();
    }

    /// <summary>
    /// Fetch one cluster's pass rate. Thin wrapper over ClusterPassRatesAsync.
    /// </summary>
    public async Task<ClusterPassRate?> ClusterPassRateAsync(
        string agentId,
        string clusterTag,
        CancellationToken ct = default)
    {
        var map = await ClusterPassRatesAsync(agentId, ct);
        return map.TryGetValue(clusterTag, out var rate) ? rate : null;
    }

    private static bool IsFeatureDisabled(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Object) return false;
        return element.TryGetProperty("status", out var s) &&
               s.ValueKind == JsonValueKind.String &&
               s.GetString() == "feature_disabled";
    }
}

/// <summary>Business-term definition from the tenant glossary.</summary>
public sealed record GlossaryTerm(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("definition")] string Definition,
    [property: JsonPropertyName("synonyms")] IReadOnlyList<string> Synonyms,
    [property: JsonPropertyName("canonical_unit")] string? CanonicalUnit,
    [property: JsonPropertyName("owner_user_id")] string? OwnerUserId,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("repository_id")] string RepositoryId,
    [property: JsonPropertyName("repository_name")] string RepositoryName,
    [property: JsonPropertyName("updated_at")] string UpdatedAt);

/// <summary>
/// Business entity from the tenant ontology (ADR-037 Step 3.5 B.2).
/// <c>Properties</c> is the full JSONB blob — tenant-authored, intentionally
/// not strongly typed since different entities carry different shapes.
/// </summary>
public sealed record OntologyEntity(
    string Id,
    string CanonicalName,
    string EntityType,
    IReadOnlyList<string> Synonyms,
    string? Description,
    string RepositoryId,
    string RepositoryName,
    JsonElement Properties,
    string Source,
    string Status,
    string UpdatedAt)
{
    public static OntologyEntity FromJson(JsonElement d)
    {
        // Kernel ships `properties` as a JSON string; parse it so agent code
        // reads nested shapes directly without a double parse.
        JsonElement parsedProps = default;
        if (d.TryGetProperty("properties", out var rawProps))
        {
            if (rawProps.ValueKind == JsonValueKind.String)
            {
                try
                {
                    parsedProps = JsonDocument.Parse(rawProps.GetString() ?? "{}").RootElement.Clone();
                }
                catch (JsonException)
                {
                    parsedProps = JsonDocument.Parse("{}").RootElement.Clone();
                }
            }
            else if (rawProps.ValueKind == JsonValueKind.Object)
            {
                parsedProps = rawProps.Clone();
            }
            else
            {
                parsedProps = JsonDocument.Parse("{}").RootElement.Clone();
            }
        }
        else
        {
            parsedProps = JsonDocument.Parse("{}").RootElement.Clone();
        }

        return new OntologyEntity(
            Id:             d.TryGetProperty("id", out var id) ? id.GetString() ?? "" : "",
            CanonicalName:  d.TryGetProperty("canonical_name", out var cn) ? cn.GetString() ?? "" : "",
            EntityType:     d.TryGetProperty("entity_type", out var et) ? et.GetString() ?? "" : "",
            Synonyms:       d.TryGetProperty("synonyms", out var sy) && sy.ValueKind == JsonValueKind.Array
                                ? sy.EnumerateArray().Select(x => x.GetString() ?? "").ToArray()
                                : Array.Empty<string>(),
            Description:    d.TryGetProperty("description", out var ds) && ds.ValueKind != JsonValueKind.Null
                                ? ds.GetString()
                                : null,
            RepositoryId:   d.TryGetProperty("repository_id", out var rid) ? rid.GetString() ?? "" : "",
            RepositoryName: d.TryGetProperty("repository_name", out var rn) ? rn.GetString() ?? "" : "",
            Properties:     parsedProps,
            Source:         d.TryGetProperty("source", out var sr) ? sr.GetString() ?? "authored" : "authored",
            Status:         d.TryGetProperty("status", out var st) ? st.GetString() ?? "active" : "active",
            UpdatedAt:      d.TryGetProperty("updated_at", out var ua) ? ua.GetString() ?? "" : "");
    }
}

/// <summary>One step of a Skill playbook.</summary>
public sealed record SkillStep(
    [property: JsonPropertyName("step_order")] int StepOrder,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("description")] string? Description,
    [property: JsonPropertyName("payload")] JsonElement Payload);

/// <summary>A named reusable playbook. Steps ordered by StepOrder ascending.</summary>
public sealed record Skill(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("description")] string? Description,
    [property: JsonPropertyName("domain")] string Domain,
    [property: JsonPropertyName("agent_binding_mask")] IReadOnlyList<string> AgentBindingMask,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("repository_id")] string RepositoryId,
    [property: JsonPropertyName("repository_name")] string RepositoryName,
    [property: JsonPropertyName("steps")] IReadOnlyList<SkillStep> Steps);

/// <summary>Per-cluster pass-rate snapshot from the most recent harness run.</summary>
public sealed record ClusterPassRate(
    [property: JsonPropertyName("cluster_tag")] string ClusterTag,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("passed")] int Passed,
    [property: JsonPropertyName("pass_rate")] double PassRate,
    [property: JsonPropertyName("run_id")] string RunId,
    [property: JsonPropertyName("recorded_at")] string RecordedAt);
