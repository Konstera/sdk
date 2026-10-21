using System.Text.Json;
using Konstera.Sdk;
using Konstera.Sdk.Internal;
using Konstera.Sdk.Services;
using Xunit;

namespace Konstera.Sdk.Tests;

/// <summary>
/// Direct-run tests for CapabilityService — verify the service surface shape
/// and that the kernel-less path raises the correct typed exception.
/// </summary>
public sealed class CapabilityTests
{
    private static AgentContext BuildCtx() =>
        AgentContext.FromEnv(new KernelMcpClient(url: null));

    [Fact]
    public async Task Available_Requires_Kernel()
    {
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Capability.AvailableAsync("orders.lookup_by_email"));
        Assert.Contains("KONSTERA_KERNEL_MCP_URL", ex.Message);
    }

    [Fact]
    public async Task Call_Requires_Kernel()
    {
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => BuildCtx().Capability.CallAsync(
                "orders.lookup_by_email",
                new Dictionary<string, object?> { ["email"] = "x@example.com" }));
        Assert.Contains("KONSTERA_KERNEL_MCP_URL", ex.Message);
    }

    [Fact]
    public void Capability_Error_Hierarchy()
    {
        // All typed sub-errors subclass CapabilityError, which subclasses
        // InvalidOperationException so defensive top-level handlers catch
        // everything via base class.
        Assert.True(typeof(CapabilityUnbound).IsSubclassOf(typeof(CapabilityError)));
        Assert.True(typeof(CapabilityUpstreamFailed).IsSubclassOf(typeof(CapabilityError)));
        Assert.True(typeof(CapabilityError).IsSubclassOf(typeof(InvalidOperationException)));
    }

    [Fact]
    public void Capability_Errors_Preserve_Inner_Cause()
    {
        var inner = new InvalidOperationException("[Unbound] Agent has no binding");
        var unbound = new CapabilityUnbound(inner.Message, inner);
        Assert.Same(inner, unbound.InnerException);
    }
}
