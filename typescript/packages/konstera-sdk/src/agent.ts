/**
 * Agent base class. Subclass, override `handle()`, done. Mirror of Python SDK's agent.py.
 */
import type { AgentContext } from "./context.js";
import type { AgentRequest, AgentResponse } from "./types.js";

/**
 * Base class every Konstera TypeScript agent extends.
 *
 * Override `handle()` (required). Optionally override `initialize()` for one-time
 * setup and `shutdown()` for cleanup.
 *
 * The SDK's `run()` function wires this up to an HTTP server + MCP client, but the
 * class itself has no coupling to the transport — agents are unit-testable without
 * spinning up any infrastructure.
 */
export abstract class Agent {
  /**
   * Called once at container startup. Load models, warm caches, open long-lived
   * connections here. Default: no-op.
   */
  async initialize(_ctx: AgentContext): Promise<void> {
    // no-op by default
  }

  /** Called for every invocation. Must be overridden. */
  async handle(_req: AgentRequest, _ctx: AgentContext): Promise<AgentResponse> {
    throw new Error(
      "Subclass Agent and override `async handle(req, ctx): Promise<AgentResponse>`.",
    );
  }

  /**
   * Called on graceful stop (SIGTERM / SIGINT). Close connections, flush buffers
   * here. Default: no-op.
   */
  async shutdown(_ctx: AgentContext): Promise<void> {
    // no-op by default
  }
}
