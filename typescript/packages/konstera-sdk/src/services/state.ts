/**
 * StateService — per-instance durable KV. Mirror of Python SDK's state.py.
 *
 * State persists across invocations and container restarts. Values are JSON —
 * objects, arrays, strings, numbers, booleans, or null all work. State is
 * per agent instance, not per invocation; use for counters, caches, cursor
 * positions, drafted-but-not-sent artifacts.
 *
 * @example
 * ```ts
 * // Increment a counter across invocations
 * const count = (await ctx.state.get<number>("processed_count")) ?? 0;
 * await ctx.state.set("processed_count", count + 1);
 *
 * // Cache structured data
 * await ctx.state.set("profile", { name: "Alice", tier: "gold" });
 * const profile = await ctx.state.get<{ name: string; tier: string }>("profile");
 * ```
 */
import type { KernelMcpClient } from "../mcp.js";

export class StateService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Fetch the value for `key`.
   *
   * @param key - Storage key. A `namespace:name` convention is useful when the
   *   agent manages multiple kinds of state, but no prefix is enforced.
   * @returns The JSON-decoded value, or `null` if the key is unset. The
   *   `T` type parameter is caller-asserted — no runtime validation.
   */
  async get<T = unknown>(key: string): Promise<T | null> {
    const result = await this.mcp.callTool("state_get", {
      instanceId: this.instanceId,
      key,
    });
    if (result.disabled) return null;
    const text = extractText(result.content);
    if (text === null || text === "null") return null;
    try {
      return JSON.parse(text) as T;
    } catch {
      return text as unknown as T;
    }
  }

  /**
   * Upsert `key = value`. Any JSON-serialisable value works. Non-JSON types
   * (Date, Map, Set) are not supported — convert explicitly first.
   */
  async set(key: string, value: unknown): Promise<void> {
    await this.mcp.callTool("state_set", {
      instanceId: this.instanceId,
      key,
      valueJson: JSON.stringify(value),
    });
  }

  /**
   * Remove `key`. Idempotent — deleting a missing key is a no-op.
   */
  async delete(key: string): Promise<void> {
    await this.mcp.callTool("state_delete", {
      instanceId: this.instanceId,
      key,
    });
  }

  /**
   * List keys, optionally filtered by prefix.
   *
   * @param prefix - Only return keys starting with this string. Empty string
   *   (the default) returns all keys.
   * @returns Sorted array of keys. Empty on no match or malformed response.
   */
  async list(prefix = ""): Promise<string[]> {
    const result = await this.mcp.callTool("state_list", {
      instanceId: this.instanceId,
      prefix,
    });
    if (result.disabled) return [];
    const text = extractText(result.content);
    if (!text) return [];
    try {
      const parsed = JSON.parse(text) as unknown;
      return Array.isArray(parsed) ? (parsed as string[]) : [];
    } catch {
      return [];
    }
  }
}

function extractText(content: Array<{ type: string; text?: string }>): string | null {
  const first = content[0];
  if (!first || first.type !== "text") return null;
  return first.text ?? null;
}
