/**
 * VectorService — RAG store wrapper. Mirror of Python SDK's vector.py.
 *
 * Namespace convention:
 * - `agent:<instance-uuid>` — private to one agent instance
 * - `shared:<name>` — shared across a tenant's agents
 *
 * @example
 * ```ts
 * // Index policy docs (once, in initialize())
 * await ctx.vector.upsert({
 *   namespace: "shared:policies",
 *   content: "Refunds within 30 days get a 100% refund.",
 *   externalId: "policy-refund-window",
 *   metadata: { source: "handbook.pdf", page: 7 },
 * });
 *
 * // Query at invocation time
 * const hits = await ctx.vector.query({
 *   namespace: "shared:policies",
 *   queryText: "customer wants refund after 2 months",
 *   topK: 3,
 * });
 * ```
 */
import type { KernelMcpClient } from "../mcp.js";

export interface VectorHit {
  readonly id: string;
  readonly externalId: string | null;
  readonly content: string;
  readonly metadata: Record<string, unknown>;
  readonly score: number;
}

export interface VectorUpsertOptions {
  namespace: string;
  content: string;
  externalId?: string;
  metadata?: Record<string, unknown>;
}

export interface VectorQueryOptions {
  namespace: string;
  queryText: string;
  topK?: number;
}

export class VectorService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Upsert a chunk into the vector store. If `externalId` is provided, a
   * later upsert with the same ID replaces the chunk.
   *
   * @returns The chunk UUID (kernel-generated) or an empty string on error.
   */
  async upsert(options: VectorUpsertOptions): Promise<string> {
    const args: Record<string, unknown> = {
      callerInstanceId: this.instanceId,
      namespace: options.namespace,
      content: options.content,
    };
    if (options.externalId !== undefined) args["externalId"] = options.externalId;
    if (options.metadata !== undefined) args["metadataJson"] = JSON.stringify(options.metadata);

    const result = await this.mcp.callTool("vector_upsert", args);
    if (result.disabled) return "";
    const text = extractText(result.content);
    if (!text) return "";
    try {
      const parsed = JSON.parse(text) as { chunkId?: string };
      return parsed.chunkId ?? "";
    } catch {
      return text;
    }
  }

  /**
   * Top-K nearest chunks by cosine similarity.
   *
   * @returns Hits ordered by descending score. Empty on no results or error.
   */
  async query(options: VectorQueryOptions): Promise<VectorHit[]> {
    const result = await this.mcp.callTool("vector_query", {
      callerInstanceId: this.instanceId,
      namespace: options.namespace,
      queryText: options.queryText,
      topK: options.topK ?? 5,
    });
    if (result.disabled) return [];
    const text = extractText(result.content);
    if (!text) return [];
    try {
      const items = JSON.parse(text) as Array<{
        id?: string;
        externalId?: string | null;
        content?: string;
        metadata?: Record<string, unknown>;
        score?: number;
      }>;
      if (!Array.isArray(items)) return [];
      return items.map((h) => ({
        id: String(h.id ?? ""),
        externalId: h.externalId ?? null,
        content: h.content ?? "",
        metadata: h.metadata ?? {},
        score: Number(h.score ?? 0),
      }));
    } catch {
      return [];
    }
  }

  /**
   * Delete a chunk by `externalId`. Idempotent.
   */
  async delete(namespace: string, externalId: string): Promise<void> {
    await this.mcp.callTool("vector_delete", {
      callerInstanceId: this.instanceId,
      namespace,
      externalId,
    });
  }
}

function extractText(content: Array<{ type: string; text?: string }>): string | null {
  const first = content[0];
  if (!first || first.type !== "text") return null;
  return first.text ?? null;
}
