/**
 * Request/response types agents receive and return. Mirror of Python SDK's types.py.
 */

/**
 * One invocation into the agent. Assembled by the SDK from the /invoke HTTP body.
 */
export interface AgentRequest {
  /** Kernel-generated ID for this invocation. Include in logs / traces. */
  readonly invocationId: string;

  /** The primary text input. Empty string is valid — agent decides what to do. */
  readonly input: string;

  /** Optional structured payload (from webhook body, structured tool call, etc.). */
  readonly payload?: Record<string, unknown> | null;

  /**
   * Per-agent-instance behaviour config. Shape declared by the manifest's `config`
   * JSON Schema; operator sets values in the portal Instance-Configuration panel.
   * Empty object when unset; always safe to access `config[key] ?? default`.
   */
  readonly config: Record<string, unknown>;
}

/**
 * What the agent returns from `handle()`. Serialised to the /invoke HTTP body.
 */
export interface AgentResponse {
  /** The primary text response. Empty string is valid but discouraged. */
  content: string;

  /** Optional structured response (for agents that produce data, not chat). */
  structured?: Record<string, unknown> | null;

  /** LLM tool calls the agent made, for observability. Populated by SDK helpers. */
  toolCalls?: Array<Record<string, unknown>>;
}
