/**
 * CostService — record non-LLM cost events. Mirror of Python's cost.py.
 *
 * LLM costs are recorded automatically by the kernel on every llm.complete.
 * Use record() for external APIs, GPU rentals, reranker calls, etc.
 */
import type { KernelMcpClient } from "../mcp.js";

export interface CostRecordOptions {
  kind: string;
  costUsd: number;
  model?: string;
  invocationId?: string;
  inputTokens?: number;
  outputTokens?: number;
  cachedInputTokens?: number;
  metadata?: Record<string, unknown>;
}

export class CostService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Record a usage event.
   *
   * Fire-and-forget — failures don't propagate.
   */
  async record(options: CostRecordOptions): Promise<void> {
    const args: Record<string, unknown> = {
      instanceId: this.instanceId,
      kind: options.kind,
      costUsd: options.costUsd,
    };
    if (options.model !== undefined) args["modelId"] = options.model;
    if (options.invocationId !== undefined) args["invocationId"] = options.invocationId;
    if (options.inputTokens !== undefined) args["inputTokens"] = options.inputTokens;
    if (options.outputTokens !== undefined) args["outputTokens"] = options.outputTokens;
    if (options.cachedInputTokens !== undefined)
      args["cachedInputTokens"] = options.cachedInputTokens;
    if (options.metadata && Object.keys(options.metadata).length > 0) {
      args["metadataJson"] = JSON.stringify(options.metadata);
    }
    await this.mcp.callTool("cost_record", args);
  }
}
