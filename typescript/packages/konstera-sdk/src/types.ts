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

/**
 * Failure categories an agent may declare. These are the four the platform
 * accepts from an agent; anything else is ignored and the failure is recorded
 * by its HTTP status (an uncategorised failure is `agent_bug`).
 *
 * - `dependency_failure`: an outside system refused or failed (a site is down,
 *   a sign-in was refused).
 * - `action_needed`: a person has a step to do first (fix a connection,
 *   approve a sign-in); the run is not retried.
 * - `input_invalid`: the input or the instance settings are wrong.
 * - `credential_missing`: a required connection or secret isn't set up.
 */
export type AgentFailureCategory =
  | "dependency_failure"
  | "action_needed"
  | "input_invalid"
  | "credential_missing";

export interface AgentFailureOptions {
  /** Defaults to `"dependency_failure"`, or the subclass's `defaultCategory`. */
  category?: AgentFailureCategory;
  /** Standard `Error` cause. */
  cause?: unknown;
}

/**
 * Throw (or subclass) to tell the platform what kind of failure this was.
 * Mirror of Python's `AgentFailure`. The runtime puts `category` in the
 * `/invoke` error body; uncategorised errors are recorded as `agent_bug`.
 * Any thrown object with a non-empty string `category` property is reported
 * the same way.
 *
 * @example
 * ```ts
 * throw new AgentFailure("The site refused the sign-in; check the connection.", {
 *   category: "action_needed",
 * });
 *
 * class SignInRefused extends AgentFailure {
 *   static override readonly defaultCategory = AgentFailure.ACTION_NEEDED;
 * }
 * ```
 */
export class AgentFailure extends Error {
  static readonly DEPENDENCY_FAILURE = "dependency_failure" as const;
  static readonly ACTION_NEEDED = "action_needed" as const;
  static readonly INPUT_INVALID = "input_invalid" as const;
  static readonly CREDENTIAL_MISSING = "credential_missing" as const;

  /** Category used when the constructor isn't given one. Override in a subclass. */
  static readonly defaultCategory: AgentFailureCategory = "dependency_failure";

  readonly category: AgentFailureCategory;

  constructor(message = "", options: AgentFailureOptions = {}) {
    super(message, options.cause !== undefined ? { cause: options.cause } : undefined);
    // Like Python's type(ex).__name__: a subclass reports its own name.
    this.name = new.target.name;
    this.category =
      options.category ?? (new.target as typeof AgentFailure).defaultCategory;
  }
}
