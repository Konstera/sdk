/**
 * RuleService — versioned, effective-dated policy registry. Mirror of
 * Python's rule.py.
 *
 * Agents READ (get, getById, list). Humans WRITE via admin HTTP endpoints.
 * Record `ruleId` in your output for reproducibility — replays should use
 * getById(ruleId) so the exact version runs regardless of newer active ones.
 */
import type { KernelMcpClient } from "../mcp.js";

export interface Rule {
  readonly ruleId: string;
  readonly ruleKey: string;
  readonly version: number;
  readonly effectiveFrom: string;
  readonly description: string | null;
  readonly proposedBy: string | null;
  readonly proposedRole: string | null;
  readonly proposedAt: string;
  readonly approvedBy: string | null;
  readonly approvedRole: string | null;
  readonly approvedAt: string | null;
  readonly decisionReason: string | null;
  readonly content: Record<string, unknown>;
}

export interface RuleSummary {
  readonly ruleKey: string;
  readonly ruleId: string;
  readonly version: number;
  readonly effectiveFrom: string;
  readonly description: string | null;
}

export class RuleService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Fetch the active rule for `ruleKey`.
   *
   * @param atTime - Optional ISO-8601 for retrospective lookup.
   */
  async get(ruleKey: string, atTime?: string): Promise<Rule | null> {
    const args: Record<string, unknown> = {
      callerInstanceId: this.instanceId,
      ruleKey,
    };
    if (atTime !== undefined) args["atTime"] = atTime;
    const result = await this.mcp.callTool("rule_get", args);
    return parseRule(result);
  }

  /** Fetch a specific rule version by its UUID. Version-pinned (reproducible). */
  async getById(ruleId: string): Promise<Rule | null> {
    const result = await this.mcp.callTool("rule_get_by_id", {
      callerInstanceId: this.instanceId,
      ruleId,
    });
    return parseRule(result);
  }

  /**
   * List rules in two modes.
   *
   * @param ruleKey - If provided, returns all versions of that key as Rule[].
   *   If omitted, returns one RuleSummary per distinct key (current active).
   * @param includeAll - Only meaningful with ruleKey. true includes draft/rejected.
   */
  async list(ruleKey?: string, includeAll = false): Promise<Rule[] | RuleSummary[]> {
    const args: Record<string, unknown> = {
      callerInstanceId: this.instanceId,
      includeAll,
    };
    if (ruleKey !== undefined) args["ruleKey"] = ruleKey;

    const result = await this.mcp.callTool("rule_list", args);
    if (result.disabled) return [];
    const text = extractText(result.content);
    if (!text) return [];
    try {
      const items = JSON.parse(text) as unknown;
      if (!Array.isArray(items)) return [];
      if (ruleKey !== undefined) {
        return items.map((d) => parseRuleDict(d as Record<string, unknown>));
      }
      return items.map((d) => parseRuleSummary(d as Record<string, unknown>));
    } catch {
      return [];
    }
  }
}

function parseRule(result: {
  disabled: boolean;
  content: Array<{ type: string; text?: string }>;
}): Rule | null {
  if (result.disabled) return null;
  const text = extractText(result.content);
  if (!text) return null;
  try {
    const d = JSON.parse(text) as Record<string, unknown>;
    return parseRuleDict(d);
  } catch {
    return null;
  }
}

function parseRuleDict(d: Record<string, unknown>): Rule {
  return {
    ruleId: String(d["ruleId"] ?? ""),
    ruleKey: String(d["ruleKey"] ?? ""),
    version: Number(d["version"] ?? 0),
    effectiveFrom: String(d["effectiveFrom"] ?? ""),
    description: (d["description"] as string | null | undefined) ?? null,
    proposedBy: (d["proposedBy"] as string | null | undefined) ?? null,
    proposedRole: (d["proposedRole"] as string | null | undefined) ?? null,
    proposedAt: String(d["proposedAt"] ?? ""),
    approvedBy: (d["approvedBy"] as string | null | undefined) ?? null,
    approvedRole: (d["approvedRole"] as string | null | undefined) ?? null,
    approvedAt: (d["approvedAt"] as string | null | undefined) ?? null,
    decisionReason: (d["decisionReason"] as string | null | undefined) ?? null,
    content: (d["content"] as Record<string, unknown> | null | undefined) ?? {},
  };
}

function parseRuleSummary(d: Record<string, unknown>): RuleSummary {
  return {
    ruleKey: String(d["ruleKey"] ?? ""),
    ruleId: String(d["ruleId"] ?? ""),
    version: Number(d["version"] ?? 0),
    effectiveFrom: String(d["effectiveFrom"] ?? ""),
    description: (d["description"] as string | null | undefined) ?? null,
  };
}

function extractText(content: Array<{ type: string; text?: string }>): string | null {
  const first = content[0];
  if (!first || first.type !== "text") return null;
  return first.text ?? null;
}
