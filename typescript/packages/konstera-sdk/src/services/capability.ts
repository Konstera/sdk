/**
 * CapabilityService — ADR-013 purpose-first indirection over connectors.
 * Mirror of Python's capability.py.
 *
 * Agents call canonical capability names (orders.lookup_by_email, tickets.reply)
 * without knowing which connector backs them. The operator binds each
 * capability to a connection at install time.
 *
 * @example
 * ```ts
 * if (await ctx.capability.available("orders.lookup_by_email")) {
 *   const orders = await ctx.capability.call("orders.lookup_by_email", {
 *     email: "customer@example.com",
 *   });
 * }
 * ```
 */
import { currentInvocationId } from "../invocation-context.js";
import type { KernelMcpClient } from "../mcp.js";

/** Base for all capability-layer errors. */
export class CapabilityError extends Error {
  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = "CapabilityError";
    if (cause !== undefined) (this as { cause?: unknown }).cause = cause;
  }
}

/** The agent has no binding for this capability in the current install. */
export class CapabilityUnbound extends CapabilityError {
  constructor(message: string, cause?: unknown) {
    super(message, cause);
    this.name = "CapabilityUnbound";
  }
}

/** The connector or REST recipe backing this capability threw. */
export class CapabilityUpstreamFailed extends CapabilityError {
  constructor(message: string, cause?: unknown) {
    super(message, cause);
    this.name = "CapabilityUpstreamFailed";
  }
}

export class CapabilityService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Check whether a capability is bound for this agent instance.
   *
   * Cheap — single DB hit. Use before calling optional capabilities to
   * avoid CapabilityUnbound. Fails closed on malformed responses.
   */
  async available(name: string): Promise<boolean> {
    const result = await this.mcp.callTool("capability_available", {
      callerInstanceId: this.instanceId,
      name,
    });
    if (result.disabled) return false;
    const text = extractText(result.content);
    if (!text) return false;
    try {
      const parsed = JSON.parse(text) as { available?: boolean };
      return parsed.available === true;
    } catch {
      return false;
    }
  }

  /**
   * Invoke a capability by canonical name.
   *
   * @param name - Canonical capability name (e.g. "orders.lookup_by_email").
   *   Kept positional-only via a dedicated parameter so args can safely
   *   contain a field also called `name` (e.g. db.proc.stats).
   * @param args - Capability-specific keyword arguments per the catalogue.
   * @returns Canonical response payload (dict, list, or scalar).
   * @throws CapabilityUnbound — no binding for this capability.
   * @throws CapabilityUpstreamFailed — upstream connector or recipe failed.
   * @throws CapabilityError — other capability-layer failures.
   */
  async call(name: string, args: Record<string, unknown> = {}): Promise<unknown> {
    const params: Record<string, unknown> = {
      callerInstanceId: this.instanceId,
      name,
      argsJson: JSON.stringify(args),
    };
    const invocationId = currentInvocationId();
    if (invocationId !== undefined) params["invocationId"] = invocationId;

    let result;
    try {
      result = await this.mcp.callTool("capability_call", params);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("[Unbound]")) throw new CapabilityUnbound(msg, e);
      if (msg.includes("[UpstreamFailed]") || msg.includes("[ResponseShapeInvalid]")) {
        throw new CapabilityUpstreamFailed(msg, e);
      }
      throw new CapabilityError(msg, e);
    }
    if (result.disabled) return null;
    const text = extractText(result.content);
    if (!text) return null;
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return text;
    }
  }
}

function extractText(content: Array<{ type: string; text?: string }>): string | null {
  const first = content[0];
  if (!first || first.type !== "text") return null;
  return first.text ?? null;
}
