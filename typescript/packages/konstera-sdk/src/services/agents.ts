/**
 * AgentsService — synchronous multi-agent invocation. Mirror of Python's agents.py.
 *
 * One agent invokes another through the kernel; the call becomes a child
 * workflow with its own audit trail. Explicit, not implicit — no autonomous
 * agent swarms.
 */
import type { KernelMcpClient } from "../mcp.js";

export interface AgentInvokeResult {
  readonly content: string;
  readonly structured: Record<string, unknown> | null;
  readonly toolCalls: Array<Record<string, unknown>>;
}

export interface AgentInvokeOptions {
  input: string;
  payload?: Record<string, unknown>;
  config?: Record<string, unknown>;
  invocationId?: string;
}

export class AgentsService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Invoke another agent synchronously.
   *
   * @param agentId - The target agent's package UUID or manifest id.
   * @param options - Input, payload, config, optional invocation ID.
   * @returns AgentInvokeResult with the called agent's response.
   */
  async invoke(agentId: string, options: AgentInvokeOptions): Promise<AgentInvokeResult> {
    const args: Record<string, unknown> = {
      callerInstanceId: this.instanceId,
      agentId,
      input: options.input,
    };
    if (options.payload !== undefined) args["payloadJson"] = JSON.stringify(options.payload);
    if (options.config !== undefined) args["configJson"] = JSON.stringify(options.config);
    if (options.invocationId !== undefined) args["invocationId"] = options.invocationId;

    const result = await this.mcp.callTool("agents_invoke", args);
    if (result.disabled) {
      return { content: "", structured: null, toolCalls: [] };
    }
    const text = extractText(result.content);
    if (!text) return { content: "", structured: null, toolCalls: [] };
    try {
      const parsed = JSON.parse(text) as {
        content?: string;
        structured?: Record<string, unknown> | null;
        toolCalls?: Array<Record<string, unknown>>;
      };
      return {
        content: parsed.content ?? "",
        structured: parsed.structured ?? null,
        toolCalls: parsed.toolCalls ?? [],
      };
    } catch {
      return { content: text, structured: null, toolCalls: [] };
    }
  }
}

function extractText(content: Array<{ type: string; text?: string }>): string | null {
  const first = content[0];
  if (!first || first.type !== "text") return null;
  return first.text ?? null;
}
