using System.Text.Json.Serialization;

namespace Konstera.Sdk;

/// <summary>
/// What the agent returns from <see cref="Agent.HandleAsync"/>.
/// Serialised to the /invoke HTTP body.
/// </summary>
public sealed class AgentResponse
{
    /// <summary>Primary text response. Empty string is valid but discouraged.</summary>
    [JsonPropertyName("content")]
    public required string Content { get; init; }

    /// <summary>Optional structured payload (for agents that produce data, not chat).</summary>
    [JsonPropertyName("structured")]
    public object? Structured { get; init; }

    /// <summary>LLM tool calls the agent made, for observability. Populated by SDK helpers when M10 lands.</summary>
    [JsonPropertyName("toolCalls")]
    public IReadOnlyList<object> ToolCalls { get; init; } = Array.Empty<object>();
}
