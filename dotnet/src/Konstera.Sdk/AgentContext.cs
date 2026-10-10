using Konstera.Sdk.Internal;
using Konstera.Sdk.Services;

namespace Konstera.Sdk;

/// <summary>
/// Object passed to every agent method. Gives the agent access to
/// identity + all kernel services, without requiring the agent to know
/// anything about how those services are wired.
///
/// Mirrors <c>konstera_sdk.AgentContext</c> in the Python SDK.
/// </summary>
public sealed class AgentContext
{
    public required string InstanceId    { get; init; }

    /// <summary>M8: tenant this instance runs under (UUID as string).
    /// Injected by the kernel at container-create time via
    /// <c>KONSTERA_TENANT_ID</c>.</summary>
    public required string TenantId      { get; init; }

    public required string AgentId       { get; init; }
    public required string AgentVersion  { get; init; }

    public required LogService         Log         { get; init; }
    public required LlmService         Llm         { get; init; }
    public required StateService       State       { get; init; }  // M7a
    public required VectorService      Vector      { get; init; }  // M7a
    public required CredentialsService Credentials { get; init; }  // M7a
    public required CostService        Cost        { get; init; }  // M7a
    public required ToolService        Tool        { get; init; }  // M7a
    public required AgentsService      Agents      { get; init; }  // M7a
    public required ArtifactService    Artifact    { get; init; }  // M7b
    public required HumanService       Human       { get; init; }  // M7c
    public required RuleService        Rule        { get; init; }  // M7d
    public required ConnectorService   Connector   { get; init; }  // ADR-009

    /// <summary>
    /// Build a context from the env vars the kernel injects at
    /// container-create time. Missing values fall back to sensible
    /// unknowns rather than raising — an agent should boot in direct-run
    /// mode with nothing set; only kernel-callback features degrade.
    /// </summary>
    public static AgentContext FromEnv(KernelMcpClient mcp, IDictionary<string, string>? defaults = null)
    {
        string Env(string key, string fallback)
            => Environment.GetEnvironmentVariable(key)
               ?? (defaults?.TryGetValue(key, out var v) == true ? v : fallback);

        var instanceId    = Env("KONSTERA_AGENT_INSTANCE_ID", "unknown-instance");
        var tenantId      = Env("KONSTERA_TENANT_ID",         "00000000-0000-0000-0000-000000000000");
        var agentId       = Env("KONSTERA_AGENT_ID",          "unknown-agent");
        var agentVersion  = Env("KONSTERA_AGENT_VERSION",     "0.0.0");

        return new AgentContext
        {
            InstanceId    = instanceId,
            TenantId      = tenantId,
            AgentId       = agentId,
            AgentVersion  = agentVersion,
            Log           = new LogService(mcp, instanceId),
            Llm           = new LlmService(mcp, instanceId),
            State         = new StateService(mcp, instanceId),
            Vector        = new VectorService(mcp, instanceId),
            Credentials   = new CredentialsService(mcp, instanceId),
            Cost          = new CostService(mcp, instanceId),
            Tool          = new ToolService(mcp),
            Agents        = new AgentsService(mcp, instanceId),
            Artifact      = new ArtifactService(mcp, instanceId),
            Human         = new HumanService(mcp, instanceId),
            Rule          = new RuleService(mcp, instanceId),
            Connector     = new ConnectorService(mcp, instanceId),
        };
    }
}
