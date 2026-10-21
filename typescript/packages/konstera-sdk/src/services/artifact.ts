/**
 * ArtifactService — content-addressed blob store. Mirror of Python's artifact.py.
 *
 * Dedup: same bytes uploaded twice produce the same sha256 (shared storage);
 * each upload still gets its own metadata row for audit. Content is
 * base64-encoded over MCP.
 */
import type { KernelMcpClient } from "../mcp.js";

export interface PutResult {
  readonly artifactId: string;
  readonly sha256: string;
  readonly sizeBytes: number;
  readonly contentType: string;
  readonly storageUri: string;
  readonly dedup: boolean;
}

export interface GetResult {
  readonly content: Uint8Array;
  readonly contentType: string;
  readonly sizeBytes: number;
  readonly sha256: string;
}

export interface HeadResult {
  readonly exists: boolean;
  readonly sha256: string;
  readonly sizeBytes: number | null;
  readonly contentType: string | null;
}

export interface ArtifactListItem {
  readonly artifactId: string;
  readonly sha256: string;
  readonly sizeBytes: number;
  readonly contentType: string;
  readonly invocationId: string | null;
  readonly uploadedAt: string;
  readonly metadata: Record<string, unknown>;
}

export interface PutOptions {
  content: Uint8Array;
  contentType: string;
  invocationId?: string;
  metadata?: Record<string, unknown>;
}

export class ArtifactService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /** Upload a blob. Returns sha256 + storage info + dedup flag. */
  async put(options: PutOptions): Promise<PutResult> {
    const args: Record<string, unknown> = {
      instanceId: this.instanceId,
      contentBase64: toBase64(options.content),
      contentType: options.contentType,
    };
    if (options.invocationId !== undefined) args["invocationId"] = options.invocationId;
    if (options.metadata && Object.keys(options.metadata).length > 0) {
      args["metadataJson"] = JSON.stringify(options.metadata);
    }

    const result = await this.mcp.callTool("artifact_put", args);
    const defaultPut: PutResult = {
      artifactId: "",
      sha256: "",
      sizeBytes: 0,
      contentType: options.contentType,
      storageUri: "",
      dedup: false,
    };
    if (result.disabled) return defaultPut;
    const text = extractText(result.content);
    if (!text) return defaultPut;
    try {
      const d = JSON.parse(text) as Record<string, unknown>;
      return {
        artifactId: String(d["artifactId"] ?? ""),
        sha256: String(d["sha256"] ?? ""),
        sizeBytes: Number(d["sizeBytes"] ?? 0),
        contentType: String(d["contentType"] ?? options.contentType),
        storageUri: String(d["storageUri"] ?? ""),
        dedup: Boolean(d["dedup"] ?? false),
      };
    } catch {
      return defaultPut;
    }
  }

  /** Download an artifact by sha256. */
  async get(sha256: string): Promise<GetResult> {
    const result = await this.mcp.callTool("artifact_get", {
      callerInstanceId: this.instanceId,
      sha256,
    });
    if (result.disabled) {
      return { content: new Uint8Array(), contentType: "", sizeBytes: 0, sha256 };
    }
    const text = extractText(result.content);
    if (!text) {
      return { content: new Uint8Array(), contentType: "", sizeBytes: 0, sha256 };
    }
    const d = JSON.parse(text) as Record<string, unknown>;
    const b64 = String(d["contentBase64"] ?? "");
    return {
      content: fromBase64(b64),
      contentType: String(d["contentType"] ?? "application/octet-stream"),
      sizeBytes: Number(d["sizeBytes"] ?? 0),
      sha256: String(d["sha256"] ?? sha256),
    };
  }

  /** Probe for an artifact without downloading. Never raises for missing. */
  async head(sha256: string): Promise<HeadResult> {
    const result = await this.mcp.callTool("artifact_head", {
      callerInstanceId: this.instanceId,
      sha256,
    });
    const defaultHead: HeadResult = { exists: false, sha256, sizeBytes: null, contentType: null };
    if (result.disabled) return defaultHead;
    const text = extractText(result.content);
    if (!text) return defaultHead;
    try {
      const d = JSON.parse(text) as Record<string, unknown>;
      return {
        exists: Boolean(d["exists"] ?? false),
        sha256: String(d["sha256"] ?? sha256),
        sizeBytes: d["sizeBytes"] !== undefined && d["sizeBytes"] !== null ? Number(d["sizeBytes"]) : null,
        contentType: (d["contentType"] as string | null | undefined) ?? null,
      };
    } catch {
      return defaultHead;
    }
  }

  /** List artifacts uploaded by an agent instance. */
  async listByUploader(
    uploaderInstanceId?: string,
    limit = 50,
  ): Promise<ArtifactListItem[]> {
    const result = await this.mcp.callTool("artifact_list_by_uploader", {
      uploaderInstanceId: uploaderInstanceId ?? this.instanceId,
      limit,
    });
    if (result.disabled) return [];
    const text = extractText(result.content);
    if (!text) return [];
    try {
      const items = JSON.parse(text) as Array<Record<string, unknown>>;
      if (!Array.isArray(items)) return [];
      return items.map((i) => ({
        artifactId: String(i["artifactId"] ?? ""),
        sha256: String(i["sha256"] ?? ""),
        sizeBytes: Number(i["sizeBytes"] ?? 0),
        contentType: String(i["contentType"] ?? ""),
        invocationId: (i["invocationId"] as string | null | undefined) ?? null,
        uploadedAt: String(i["uploadedAt"] ?? ""),
        metadata: (i["metadata"] as Record<string, unknown> | null | undefined) ?? {},
      }));
    } catch {
      return [];
    }
  }
}

function toBase64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64");
}

function fromBase64(b64: string): Uint8Array {
  return new Uint8Array(Buffer.from(b64, "base64"));
}

function extractText(content: Array<{ type: string; text?: string }>): string | null {
  const first = content[0];
  if (!first || first.type !== "text") return null;
  return first.text ?? null;
}
