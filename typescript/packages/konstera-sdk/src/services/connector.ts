/**
 * ConnectorService — ADR-009 connector framework surface. Mirror of
 * Python's connector.py.
 *
 * Agents call granted connections by alias. The tenant admin configures
 * the connection and grants this agent access.
 */
import type { KernelMcpClient } from "../mcp.js";

export interface ConnectorGrant {
  readonly alias: string;
  readonly connectorTypeKey: string;
  readonly connectionId: string;
  readonly scope: Record<string, unknown>;
}

export class ConnectorService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /** List connections this agent has been granted. */
  async list(): Promise<ConnectorGrant[]> {
    const result = await this.mcp.callTool("connector_list", {
      callerInstanceId: this.instanceId,
    });
    if (result.disabled) return [];
    const text = extractText(result.content);
    if (!text) return [];
    try {
      const items = JSON.parse(text) as Array<{
        alias?: string;
        connectorTypeKey?: string;
        connectionId?: string;
        scope?: Record<string, unknown>;
      }>;
      if (!Array.isArray(items)) return [];
      return items.map((g) => ({
        alias: g.alias ?? "",
        connectorTypeKey: g.connectorTypeKey ?? "",
        connectionId: g.connectionId ?? "",
        scope: g.scope ?? {},
      }));
    } catch {
      return [];
    }
  }

  /**
   * Invoke a granted connection.
   *
   * @param alias - Tenant-configured connection name (e.g. "shopify_uk").
   * @param method - Connector-type-specific operation (e.g. "query", "list_products").
   * @param args - JSON-serialisable args for the method.
   * @returns Connector method's response. Empty object for empty response.
   */
  async call(
    alias: string,
    method: string,
    args: Record<string, unknown> = {},
  ): Promise<unknown> {
    const result = await this.mcp.callTool("connector_call", {
      callerInstanceId: this.instanceId,
      alias,
      method,
      argsJson: JSON.stringify(args),
    });
    if (result.disabled) return {};
    const text = extractText(result.content);
    if (!text) return {};
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
