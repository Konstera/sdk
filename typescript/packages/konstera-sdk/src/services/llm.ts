/**
 * LlmService — provider-agnostic LLM completion via the kernel's llm_complete MCP
 * tool. Mirror of Python SDK's llm.py. The kernel owns cost metering + provider
 * routing (ADR-011); the SDK is a thin wrapper.
 */
import type { KernelCallResult, KernelMcpClient } from "../mcp.js";

export interface LlmUsage {
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
}

export interface LlmResult {
  text: string;
  usage: LlmUsage;
}

export interface LlmCompleteOptions {
  /** Model identifier the kernel routes to. e.g. "claude-sonnet-4-6", "gpt-5". */
  model: string;
  /** Prompt / messages concatenated. See LlmMessage for structured form. */
  prompt: string;
  /** Max output tokens. Defaults to provider-side limit when unset. */
  maxTokens?: number;
  /** Sampling temperature (0..1). Defaults to provider default when unset. */
  temperature?: number;
}

export class LlmService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Request a completion. In direct-run mode returns a stub result so agents can
   * boot and exercise code paths without a live kernel; the stub's text is empty
   * and usage is zero.
   */
  async complete(options: LlmCompleteOptions): Promise<LlmResult> {
    const result = await this.mcp.callTool("llm_complete", {
      callerInstanceId: this.instanceId,
      model: options.model,
      prompt: options.prompt,
      maxTokens: options.maxTokens,
      temperature: options.temperature,
    });

    if (result.disabled) {
      return { text: "", usage: { inputTokens: 0, outputTokens: 0, costUsd: 0 } };
    }

    return parseLlmResult(result);
  }
}

function parseLlmResult(result: KernelCallResult): LlmResult {
  const first = result.content[0];
  if (!first || first.type !== "text" || !first.text) {
    return { text: "", usage: { inputTokens: 0, outputTokens: 0, costUsd: 0 } };
  }
  try {
    const parsed = JSON.parse(first.text) as {
      text?: string;
      usage?: { inputTokens?: number; outputTokens?: number; costUsd?: number };
    };
    return {
      text: parsed.text ?? "",
      usage: {
        inputTokens: parsed.usage?.inputTokens ?? 0,
        outputTokens: parsed.usage?.outputTokens ?? 0,
        costUsd: parsed.usage?.costUsd ?? 0,
      },
    };
  } catch {
    return { text: first.text, usage: { inputTokens: 0, outputTokens: 0, costUsd: 0 } };
  }
}
