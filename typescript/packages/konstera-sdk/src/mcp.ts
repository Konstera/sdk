/**
 * KernelMcpClient — thin wrapper around the @modelcontextprotocol/sdk Client that
 * matches the Python SDK's _mcp.py semantics. Centralises the direct-run-mode
 * behaviour (callbacks become no-ops when KONSTERA_KERNEL_MCP_URL is unset) so
 * individual services don't have to repeat the check.
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

/**
 * Result of a kernel MCP tool call. Shape mirrors the MCP ToolResult (content
 * array of text blocks). In direct-run mode this is an empty-content stub.
 */
export interface KernelCallResult {
  readonly disabled: boolean;
  readonly content: Array<{ type: string; text?: string }>;
}

export class KernelMcpClient {
  private readonly url: string | undefined;
  private client: Client | undefined;
  private connecting: Promise<void> | undefined;

  constructor(url: string | undefined) {
    this.url = url;
  }

  /** True when the kernel URL is set (i.e. not direct-run mode). */
  get enabled(): boolean {
    return !!this.url;
  }

  /**
   * Call a kernel tool by name with a JSON-serialisable argument bag.
   *
   * In direct-run mode (no URL): emits a console warning on first call and returns
   * a disabled stub. Agents can keep running; only the kernel-side side effect
   * (log row, llm call, state write) is lost.
   */
  async callTool(name: string, args: Record<string, unknown>): Promise<KernelCallResult> {
    if (!this.url) {
      warnOnceDirectRun();
      return { disabled: true, content: [] };
    }

    await this.ensureConnected();
    if (!this.client) {
      // Should be unreachable — ensureConnected() throws or sets client.
      return { disabled: true, content: [] };
    }

    const result = await this.client.callTool({ name, arguments: args });
    return {
      disabled: false,
      content: (result.content as Array<{ type: string; text?: string }>) ?? [],
    };
  }

  /**
   * Call a kernel tool where the agent needs the result. Mirror of Python's
   * `call_tool_for_result`: unlike {@link callTool} it throws in direct-run
   * mode, and throws when the kernel reports the tool failed (`isError`),
   * with the kernel's message (including any "[Code] ..." prefix).
   *
   * @returns The concatenated text content, or null when there is none.
   */
  async callToolForResult(name: string, args: Record<string, unknown>): Promise<string | null> {
    if (!this.url) {
      throw new Error(
        `Cannot call MCP tool '${name}' — KONSTERA_KERNEL_MCP_URL is unset. ` +
          "This is expected in direct-run mode; the agent should guard " +
          "against it or run inside a Konstera kernel.",
      );
    }
    await this.ensureConnected();
    if (!this.client) {
      throw new Error(`Cannot call MCP tool '${name}' — kernel MCP client is not connected.`);
    }
    const result = await this.client.callTool({ name, arguments: args });
    return toolResultText(name, result as { content?: unknown; isError?: unknown });
  }

  private async ensureConnected(): Promise<void> {
    if (this.client) return;
    if (this.connecting) {
      await this.connecting;
      return;
    }
    this.connecting = this.connect();
    try {
      await this.connecting;
    } finally {
      this.connecting = undefined;
    }
  }

  private async connect(): Promise<void> {
    if (!this.url) return;
    const transport = new StreamableHTTPClientTransport(new URL(this.url));
    const client = new Client(
      { name: "konstera-sdk-typescript", version: "0.1.0" },
      { capabilities: {} },
    );
    await client.connect(transport);
    this.client = client;
  }
}

/**
 * Text of a CallToolResult, or throw if the tool reported an error. Mirror of
 * Python's `tool_result_text`: MCP reports a failed tool as a normal result
 * with isError=true, so returning that text as data would hide the failure.
 */
export function toolResultText(
  name: string,
  result: { content?: unknown; isError?: unknown },
): string | null {
  const blocks = Array.isArray(result.content)
    ? (result.content as Array<{ text?: unknown }>)
    : [];
  const texts = blocks.filter((c) => typeof c?.text === "string").map((c) => c.text as string);
  const text = texts.length ? texts.join("") : null;
  if (result.isError) {
    throw new Error(text || `MCP tool '${name}' failed without an error message.`);
  }
  return text;
}

let directRunWarningEmitted = false;
function warnOnceDirectRun(): void {
  if (directRunWarningEmitted) return;
  directRunWarningEmitted = true;
  // eslint-disable-next-line no-console
  console.warn(
    "[konstera-sdk] KONSTERA_KERNEL_MCP_URL not set — kernel callbacks disabled (direct-run mode).",
  );
}
