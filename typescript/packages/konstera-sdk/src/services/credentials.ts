/**
 * CredentialsService — tenant-scoped secret resolver. Mirror of Python's
 * credentials.py.
 *
 * The kernel resolves tenant from the caller instance ID — agents never see
 * the resolution logic. **Never log or echo the value** returned from
 * `get(key)` into prompts, outputs, or structured responses.
 *
 * @example
 * ```ts
 * const stripeKey = await ctx.credentials.get("stripe-api-key");
 * // Use the key for its intended purpose — never ctx.log.info(stripeKey)
 * ```
 */
import type { KernelMcpClient } from "../mcp.js";

export class CredentialsService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Resolve a credential by key.
   *
   * @param key - Logical credential name (e.g. `"stripe-api-key"`). The tenant
   *   admin configures these in the portal; the kernel resolves to the actual
   *   secret value.
   * @returns The secret value. Empty string in direct-run mode (no kernel).
   * @throws RuntimeError via the kernel if the key doesn't exist.
   */
  async get(key: string): Promise<string> {
    const result = await this.mcp.callTool("credentials_get", {
      callerInstanceId: this.instanceId,
      key,
    });
    if (result.disabled) return "";
    const first = result.content[0];
    if (!first || first.type !== "text") return "";
    return first.text ?? "";
  }
}
