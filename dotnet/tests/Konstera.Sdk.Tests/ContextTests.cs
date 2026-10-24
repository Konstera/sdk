using Konstera.Sdk;
using Konstera.Sdk.Internal;
using Konstera.Sdk.Services;
using Xunit;

namespace Konstera.Sdk.Tests;

/// <summary>
/// Direct-run-mode tests for the SDK's service surface. These don't hit a
/// live kernel — they exercise the SDK's shape and the no-kernel fallback
/// semantics. Mirrors <c>test_services.py</c> in sdk/python.
/// </summary>
public sealed class ContextTests
{
    private static AgentContext BuildCtx() =>
        AgentContext.FromEnv(new KernelMcpClient(url: null));

    [Fact]
    public void Context_Exposes_All_M7_Services()
    {
        var ctx = BuildCtx();
        Assert.NotNull(ctx.Log);
        Assert.NotNull(ctx.Llm);
        Assert.NotNull(ctx.State);
        Assert.NotNull(ctx.Vector);
        Assert.NotNull(ctx.Credentials);
        Assert.NotNull(ctx.Cost);
        Assert.NotNull(ctx.Tool);
        Assert.NotNull(ctx.Agents);
        Assert.NotNull(ctx.Artifact);
        Assert.NotNull(ctx.Human);
        Assert.NotNull(ctx.Rule);
        Assert.NotNull(ctx.Connector);
        Assert.NotNull(ctx.Capability);
        Assert.NotNull(ctx.Semantic);
    }

    [Fact]
    public async Task Connector_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Connector.ListAsync());
    }

    [Fact]
    public async Task State_Requires_Kernel()
    {
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().State.GetAsync("some-key"));
        Assert.Contains("KONSTERA_KERNEL_MCP_URL", ex.Message);
    }

    [Fact]
    public async Task Vector_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Vector.QueryAsync("agent:foo", "hello"));
    }

    [Fact]
    public async Task Credentials_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Credentials.GetAsync("SOME_KEY"));
    }

    [Fact]
    public async Task Cost_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Cost.RecordAsync(kind: "tool", costUsd: 0.01));
    }

    [Fact]
    public async Task CostSummary_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Cost.SummaryAsync(windowHours: 24));
    }

    [Fact]
    public async Task CostSummary_Rejects_Window_Below_One()
    {
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => BuildCtx().Cost.SummaryAsync(windowHours: 0));
    }

    [Fact]
    public async Task Tool_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Tool.ListAsync());
    }

    [Fact]
    public async Task Agents_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Agents.InvokeAsync(
                "00000000-0000-0000-0000-000000000000", input: "hi"));
    }

    [Fact]
    public async Task Artifact_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Artifact.PutAsync(
                new byte[] { 1, 2, 3 }, contentType: "application/octet-stream"));
    }

    [Fact]
    public async Task Human_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Human.RequestAsync(new HumanRequestOptions(
                Kind: "test", Tier: "T3", Summary: "nope")));
    }

    [Fact]
    public async Task Rule_Requires_Kernel()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Rule.GetAsync("some-key"));
    }

    [Fact]
    public async Task Log_NoOps_In_DirectRun_Mode()
    {
        // Log calls tolerate a missing kernel (fire-and-forget with warning),
        // unlike state/vector/etc. which propagate the error.
        await BuildCtx().Log.InfoAsync("this must not raise");
    }
}
