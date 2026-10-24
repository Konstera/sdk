/**
 * CostService — record non-LLM cost events + read rolling spend summaries.
 * Mirror of Python's cost.py.
 *
 * LLM costs are recorded automatically by the kernel on every llm.complete.
 * Use record() for external APIs, GPU rentals, reranker calls, etc.
 * Use summary() to self-govern against a budget without maintaining your
 * own counters.
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

/** Rolling cost summary across a time window for this instance. */
export interface CostSummary {
  /** The window the summary covers (as requested). */
  readonly windowHours: number;
  /** ISO-8601 start of the window (UTC). */
  readonly since: string;
  /** ISO-8601 end of the window (UTC), typically ~now. */
  readonly until: string;
  /** Sum of costUsd across every usage_event in the window. */
  readonly totalUsd: number;
  /** Totals bucketed by `kind` — llm, tool, connector, other. */
  readonly byKind: Record<string, number>;
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

  /**
   * Fetch this agent instance's rolling cost over the past N hours.
   *
   * Useful for self-governing agents that want to cap spend without
   * maintaining their own counters. Returns null if the window is empty
   * or the kernel doesn't yet expose the `cost_summary` MCP tool.
   *
   * @param windowHours Lookback window; must be >= 1. Defaults to 24.
   */
  async summary(windowHours = 24): Promise<CostSummary | null> {
    if (windowHours < 1) {
      throw new Error("windowHours must be >= 1");
    }
    const result = await this.mcp.callTool("cost_summary", {
      instanceId: this.instanceId,
      windowHours,
    });
    if (result.disabled) return null;
    const text = extractText(result.content);
    if (!text || text === "null") return null;
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch {
      return null;
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) return null;
    const d = data as Record<string, unknown>;
    const byKindRaw = (d["by_kind"] ?? {}) as Record<string, unknown>;
    const byKind: Record<string, number> = {};
    for (const [k, v] of Object.entries(byKindRaw)) byKind[k] = Number(v) || 0;
    return {
      windowHours: Number(d["window_hours"]) || 0,
      since: String(d["since"] ?? ""),
      until: String(d["until"] ?? ""),
      totalUsd: Number(d["total_usd"]) || 0,
      byKind,
    };
  }
}

/** Local copy of the extractText helper used across services (see semantic.ts). */
function extractText(content: Array<{ type: string; text?: string }>): string | null {
  if (!Array.isArray(content)) return null;
  for (const block of content) {
    if (block.type === "text" && typeof block.text === "string") return block.text;
  }
  return null;
}
