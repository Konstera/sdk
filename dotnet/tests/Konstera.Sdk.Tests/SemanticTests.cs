using System.Text.Json;
using Konstera.Sdk;
using Konstera.Sdk.Internal;
using Konstera.Sdk.Services;
using Xunit;

namespace Konstera.Sdk.Tests;

/// <summary>
/// Direct-run tests for SemanticService (ADR-037) — glossary, ontology,
/// skills, cluster pass rates. Also exercises the dataclass shapes.
/// </summary>
public sealed class SemanticTests
{
    private static AgentContext BuildCtx() =>
        AgentContext.FromEnv(new KernelMcpClient(url: null));

    [Fact]
    public async Task GlossaryLookup_Requires_Kernel()
    {
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Semantic.GlossaryLookupAsync("refund_window_days"));
        Assert.Contains("KONSTERA_KERNEL_MCP_URL", ex.Message);
    }

    [Fact]
    public async Task OntologyLookup_Requires_Kernel()
    {
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Semantic.OntologyLookupAsync("customer"));
        Assert.Contains("KONSTERA_KERNEL_MCP_URL", ex.Message);
    }

    [Fact]
    public async Task SkillsGet_Requires_Kernel()
    {
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Semantic.SkillsGetAsync("evaluate_refund_eligibility"));
        Assert.Contains("KONSTERA_KERNEL_MCP_URL", ex.Message);
    }

    [Fact]
    public async Task ClusterPassRates_Requires_Kernel()
    {
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Semantic.ClusterPassRatesAsync("some-agent-id"));
        Assert.Contains("KONSTERA_KERNEL_MCP_URL", ex.Message);
    }

    [Fact]
    public void OntologyEntity_FromJson_Parses_Properties_JsonString()
    {
        // Properties ships as a JSON string on the wire — we parse it so
        // agent code reads nested shapes directly.
        var props = """
            {
              "identity": {
                "primary": {"field": "email", "capability": "customers.lookup_by_email"}
              }
            }
        """;
        var payload = JsonSerializer.Serialize(new
        {
            id = "e-1",
            canonical_name = "customer",
            entity_type = "person",
            synonyms = Array.Empty<string>(),
            description = (string?)null,
            repository_id = "r",
            repository_name = "retail",
            properties = props,  // string, not object
            source = "authored",
            status = "active",
            updated_at = "x",
        });
        using var doc = JsonDocument.Parse(payload);
        var entity = OntologyEntity.FromJson(doc.RootElement);

        Assert.Equal("customer", entity.CanonicalName);
        Assert.Equal(JsonValueKind.Object, entity.Properties.ValueKind);
        var identity = entity.Properties.GetProperty("identity");
        Assert.Equal("email", identity.GetProperty("primary").GetProperty("field").GetString());
    }

    [Fact]
    public void OntologyEntity_FromJson_Accepts_Properties_Already_Dict()
    {
        // When properties arrives as a nested object (not a JSON string),
        // we accept it verbatim.
        var payload = JsonSerializer.Serialize(new
        {
            id = "e-1",
            canonical_name = "order",
            entity_type = "object",
            synonyms = Array.Empty<string>(),
            description = (string?)null,
            repository_id = "r",
            repository_name = "retail",
            properties = new { key_attributes = new { total_usd = new { type = "number", min = 0 } } },
            source = "authored",
            status = "active",
            updated_at = "x",
        });
        using var doc = JsonDocument.Parse(payload);
        var entity = OntologyEntity.FromJson(doc.RootElement);

        Assert.Equal("order", entity.CanonicalName);
        Assert.Equal("number", entity.Properties.GetProperty("key_attributes").GetProperty("total_usd").GetProperty("type").GetString());
    }

    [Fact]
    public void OntologyEntity_FromJson_Null_Properties_Defaults_To_Empty_Object()
    {
        var payload = JsonSerializer.Serialize(new
        {
            id = "e-1",
            canonical_name = "sku",
            entity_type = "object",
            synonyms = Array.Empty<string>(),
            repository_id = "r",
            repository_name = "retail",
            source = "authored",
            status = "active",
            updated_at = "x",
            // properties omitted
        });
        using var doc = JsonDocument.Parse(payload);
        var entity = OntologyEntity.FromJson(doc.RootElement);

        Assert.Equal(JsonValueKind.Object, entity.Properties.ValueKind);
        Assert.Empty(entity.Properties.EnumerateObject());
    }
}
