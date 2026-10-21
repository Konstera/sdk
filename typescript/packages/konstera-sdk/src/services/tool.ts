/**
 * ToolService — call platform-provided tools by name. Mirror of Python's tool.py.
 *
 * M7a ships: datetime_now, datetime_parse, hash_sha256, uuid_new, json_validate.
 * Discover the full set at runtime with list().
 */
import type { KernelMcpClient } from "../mcp.js";

export interface ToolDescriptor {
  readonly name: string;
  readonly description: string;
}

export class ToolService {
  private readonly mcp: KernelMcpClient;

  constructor(mcp: KernelMcpClient) {
    this.mcp = mcp;
  }

  /** List platform tools available to this agent. */
  async list(): Promise<ToolDescriptor[]> {
    const result = await this.mcp.callTool("tool_list", {});
    if (result.disabled) return [];
    const text = extractText(result.content);
    if (!text) return [];
    try {
      const items = JSON.parse(text) as unknown;
      return Array.isArray(items) ? (items as ToolDescriptor[]) : [];
    } catch {
      return [];
    }
  }

  /**
   * Invoke a platform tool.
   *
   * @returns Decoded JSON result, raw string for non-JSON responses, or null
   *   for an empty response.
   */
  async call(name: string, args: Record<string, unknown> = {}): Promise<unknown> {
    const result = await this.mcp.callTool("tool_call", {
      name,
      argsJson: JSON.stringify(args),
    });
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
