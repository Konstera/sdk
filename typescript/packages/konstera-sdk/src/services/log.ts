/**
 * LogService — structured logging back to the kernel via MCP. Mirror of Python
 * SDK's logging.py. Fire-and-forget semantics; kernel-side writes land in
 * invocation_logs; direct-run mode is a no-op.
 */
import { currentInvocationId } from "../invocation-context.js";
import type { KernelMcpClient } from "../mcp.js";

export class LogService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  async info(message: string, fields: Record<string, unknown> = {}): Promise<void> {
    await this.mcp.callTool("log_info", this.payload(message, fields));
  }

  async warn(message: string, fields: Record<string, unknown> = {}): Promise<void> {
    await this.mcp.callTool("log_warn", this.payload(message, fields));
  }

  async error(message: string, fields: Record<string, unknown> = {}): Promise<void> {
    await this.mcp.callTool("log_error", this.payload(message, fields));
  }

  private payload(message: string, fields: Record<string, unknown>): Record<string, unknown> {
    const payload: Record<string, unknown> = {
      callerInstanceId: this.instanceId,
      message,
      fields: Object.keys(fields).length > 0 ? JSON.stringify(fields) : "{}",
    };
    const invId = currentInvocationId();
    if (invId) {
      payload["invocationId"] = invId;
    }
    return payload;
  }
}
