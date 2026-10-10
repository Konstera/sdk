using System.Text.Json;
using System.Text.Json.Serialization;

namespace Konstera.Sdk;

/// <summary>
/// One invocation into the agent. Assembled by the SDK from the /invoke
/// HTTP body. Mirrors <c>konstera_sdk.AgentRequest</c> in the Python SDK.
/// </summary>
public sealed record AgentRequest(
    [property: JsonPropertyName("invocationId")] string InvocationId,
    [property: JsonPropertyName("input")]        string Input,
    [property: JsonPropertyName("payload")]      JsonElement? Payload = null);
