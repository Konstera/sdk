/**
 * HumanService — human-in-the-loop approvals with tier-based routing + SoD.
 * Mirror of Python's human.py.
 *
 * Tier semantics:
 * - T0 Blocked      — kernel refuses at submission
 * - T1 Prepare-only — sits pending until a human acts
 * - T2 Auto-stage   — auto-approved by kernel; audit preserved
 * - T3 Straight-through — auto-approved on mature whitelisted rule
 */
import type { KernelMcpClient } from "../mcp.js";

export type Tier = "T0" | "T1" | "T2" | "T3";
export type Status =
  | "pending"
  | "approved"
  | "rejected"
  | "reworked"
  | "blocked"
  | "expired";
export type Decision = "approve" | "reject" | "rework";

export interface HumanDecision {
  readonly approvalId: string;
  readonly kind: string;
  readonly tier: Tier;
  readonly status: Status;
  readonly summary: string;
  readonly submitterInstanceId: string;
  readonly submitterRole: string | null;
  readonly invocationId: string | null;
  readonly options: string[];
  readonly decision: Decision | null;
  readonly approverActorId: string | null;
  readonly approverRole: string | null;
  readonly decisionReason: string | null;
  readonly submittedAt: string;
  readonly decidedAt: string | null;
  readonly expiresAt: string | null;
  readonly detail: Record<string, unknown>;
}

/** True if the approval has left the pending state. */
export function isResolved(d: HumanDecision): boolean {
  return d.status !== "pending";
}

/** True if the approval is approved. */
export function isApproved(d: HumanDecision): boolean {
  return d.status === "approved";
}

export interface HumanRequestOptions {
  kind: string;
  tier: Tier;
  summary: string;
  detail?: Record<string, unknown>;
  options?: string[];
  submitterRole?: string;
  invocationId?: string;
  waitSeconds?: number;
  parentApprovalId?: string;
}

export class HumanService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /** Submit an approval request. */
  async request(options: HumanRequestOptions): Promise<HumanDecision> {
    const args: Record<string, unknown> = {
      instanceId: this.instanceId,
      kind: options.kind,
      tier: options.tier,
      summary: options.summary,
    };
    if (options.detail !== undefined) args["detailJson"] = JSON.stringify(options.detail);
    if (options.options !== undefined) args["optionsJson"] = JSON.stringify(options.options);
    if (options.submitterRole !== undefined) args["submitterRole"] = options.submitterRole;
    if (options.invocationId !== undefined) args["invocationId"] = options.invocationId;
    if (options.parentApprovalId !== undefined)
      args["parentApprovalId"] = options.parentApprovalId;

    const result = await this.mcp.callTool("human_submit", args);
    let decision = parseDecision(result);

    // Client-side poll — only useful for T1
    if (options.waitSeconds && decision.status === "pending") {
      decision = await this.wait(decision.approvalId, options.waitSeconds);
    }
    return decision;
  }

  /** Fetch the current state of an approval. */
  async get(approvalId: string): Promise<HumanDecision> {
    const result = await this.mcp.callTool("human_get", {
      callerInstanceId: this.instanceId,
      approvalId,
    });
    return parseDecision(result);
  }

  /** Poll for a decision. 1–60 seconds. */
  async wait(approvalId: string, timeoutSeconds = 30): Promise<HumanDecision> {
    const result = await this.mcp.callTool("human_wait", {
      callerInstanceId: this.instanceId,
      approvalId,
      timeoutSeconds,
    });
    return parseDecision(result);
  }

  /** List pending approvals. */
  async listPending(mineOnly = false, limit = 50): Promise<HumanDecision[]> {
    const args: Record<string, unknown> = {
      callerInstanceId: this.instanceId,
      limit,
    };
    if (mineOnly) args["submitterInstanceId"] = this.instanceId;
    const result = await this.mcp.callTool("human_list_pending", args);
    if (result.disabled) return [];
    const text = extractText(result.content);
    if (!text) return [];
    try {
      const items = JSON.parse(text) as Array<Record<string, unknown>>;
      if (!Array.isArray(items)) return [];
      return items.map(parseDecisionDict);
    } catch {
      return [];
    }
  }
}

function parseDecision(result: {
  disabled: boolean;
  content: Array<{ type: string; text?: string }>;
}): HumanDecision {
  if (result.disabled) return emptyDecision();
  const text = extractText(result.content);
  if (!text) return emptyDecision();
  try {
    const d = JSON.parse(text) as Record<string, unknown>;
    return parseDecisionDict(d);
  } catch {
    return emptyDecision();
  }
}

function parseDecisionDict(d: Record<string, unknown>): HumanDecision {
  return {
    approvalId: String(d["approvalId"] ?? ""),
    kind: String(d["kind"] ?? ""),
    tier: (d["tier"] as Tier | undefined) ?? "T1",
    status: (d["status"] as Status | undefined) ?? "pending",
    summary: String(d["summary"] ?? ""),
    submitterInstanceId: String(d["submitterInstanceId"] ?? ""),
    submitterRole: (d["submitterRole"] as string | null | undefined) ?? null,
    invocationId: (d["invocationId"] as string | null | undefined) ?? null,
    options: (d["options"] as string[] | undefined) ?? [],
    decision: (d["decision"] as Decision | null | undefined) ?? null,
    approverActorId: (d["approverActorId"] as string | null | undefined) ?? null,
    approverRole: (d["approverRole"] as string | null | undefined) ?? null,
    decisionReason: (d["decisionReason"] as string | null | undefined) ?? null,
    submittedAt: String(d["submittedAt"] ?? ""),
    decidedAt: (d["decidedAt"] as string | null | undefined) ?? null,
    expiresAt: (d["expiresAt"] as string | null | undefined) ?? null,
    detail: (d["detail"] as Record<string, unknown> | null | undefined) ?? {},
  };
}

function emptyDecision(): HumanDecision {
  return {
    approvalId: "",
    kind: "",
    tier: "T1",
    status: "pending",
    summary: "",
    submitterInstanceId: "",
    submitterRole: null,
    invocationId: null,
    options: [],
    decision: null,
    approverActorId: null,
    approverRole: null,
    decisionReason: null,
    submittedAt: "",
    decidedAt: null,
    expiresAt: null,
    detail: {},
  };
}

function extractText(content: Array<{ type: string; text?: string }>): string | null {
  const first = content[0];
  if (!first || first.type !== "text") return null;
  return first.text ?? null;
}
