using Konstera.Sdk.Internal;

namespace Konstera.Sdk.Services;

/// <summary>
/// Tenant-scoped opaque secret resolver. Never log the value received here.
///
/// M8: caller instance UUID is injected on every call so the kernel can
/// resolve the tenant. Agent authors don't see this — captured in the
/// constructor and forwarded automatically.
/// </summary>
public sealed class CredentialsService
{
    private readonly KernelMcpClient _mcp;
    private readonly string _instanceId;

    public CredentialsService(KernelMcpClient mcp, string instanceId)
    {
        _mcp = mcp;
        _instanceId = instanceId;
    }

    public async Task<string> GetAsync(string key, CancellationToken ct = default)
    {
        var raw = await _mcp.CallToolForResultAsync(
            "credentials_get",
            new Dictionary<string, object?>
            {
                ["callerInstanceId"] = _instanceId,
                ["key"] = key,
            },
            ct);
        return raw ?? "";
    }
}
