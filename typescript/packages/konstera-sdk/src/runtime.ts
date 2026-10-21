/**
 * The `run()` entry point — hosts the agent as an HTTP server. Mirror of Python
 * SDK's runtime.py. Deliberately uses the Node built-in http module (no Express /
 * Fastify dep) to keep the install footprint small; agents don't need a web
 * framework for three endpoints.
 */
import { IncomingMessage, Server, ServerResponse, createServer } from "node:http";

import type { Agent } from "./agent.js";
import { createContext } from "./context.js";
import { enterInvocation } from "./invocation-context.js";
import { KernelMcpClient } from "./mcp.js";
import type { AgentRequest, AgentResponse } from "./types.js";

export interface RunOptions {
  /** HTTP port. Defaults to 8080 (matches Python / .NET SDK convention). */
  port?: number;
}

/**
 * Host `agent` as an HTTP server. Resolves when the server starts listening;
 * installs SIGTERM / SIGINT handlers so the process stays alive until stopped.
 *
 * Reads KONSTERA_KERNEL_MCP_URL + KONSTERA_AGENT_* env vars set by the kernel's
 * ContainerAgentHost at container-create time. Runs in direct-run mode (env unset)
 * where kernel-callback services become no-ops.
 */
export async function run(agent: Agent, options: RunOptions = {}): Promise<void> {
  const port = options.port ?? 8080;

  const mcpUrl = process.env["KONSTERA_KERNEL_MCP_URL"];
  const mcp = new KernelMcpClient(mcpUrl);
  const ctx = createContext(mcp);

  if (mcp.enabled) {
    // eslint-disable-next-line no-console
    console.log(`[konstera-sdk] Kernel MCP URL: ${mcpUrl}`);
  } else {
    // eslint-disable-next-line no-console
    console.warn(
      "[konstera-sdk] KONSTERA_KERNEL_MCP_URL not set — kernel callbacks disabled (direct-run mode).",
    );
  }

  await agent.initialize(ctx);

  const server = createServer(async (req, res) => {
    try {
      if (req.method === "GET" && req.url === "/health") {
        return respondJson(res, 200, {
          status: "ok",
          agent: ctx.agentId,
          version: ctx.agentVersion,
        });
      }
      if (req.method === "GET" && req.url === "/describe") {
        return respondJson(res, 200, {
          id: ctx.agentId,
          version: ctx.agentVersion,
          capabilities: ["kernel-mcp-callback"],
          tools: [],
        });
      }
      if (req.method === "POST" && req.url === "/invoke") {
        return handleInvoke(req, res, agent, ctx);
      }
      return respondJson(res, 404, { error: { type: "NotFound", message: req.url ?? "" } });
    } catch (err) {
      return respondJson(res, 500, {
        error: {
          type: err instanceof Error ? err.name : "Error",
          message: err instanceof Error ? err.message : String(err),
        },
      });
    }
  });

  await listen(server, port);

  const shutdown = async (signal: string): Promise<void> => {
    // eslint-disable-next-line no-console
    console.log(`[konstera-sdk] ${signal} received — shutting down.`);
    server.close();
    try {
      await agent.shutdown(ctx);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("[konstera-sdk] agent.shutdown() threw:", err);
    }
    process.exit(0);
  };

  process.on("SIGTERM", () => void shutdown("SIGTERM"));
  process.on("SIGINT", () => void shutdown("SIGINT"));

  // eslint-disable-next-line no-console
  console.log(`[konstera-sdk] agent ${ctx.agentId}@${ctx.agentVersion} listening on :${port}`);
}

async function handleInvoke(
  req: IncomingMessage,
  res: ServerResponse,
  agent: Agent,
  ctx: ReturnType<typeof createContext>,
): Promise<void> {
  const body = await readJsonBody(req);
  const agentRequest: AgentRequest = {
    invocationId: String(body["invocationId"] ?? "missing"),
    input: String(body["input"] ?? ""),
    payload: (body["payload"] as Record<string, unknown> | null | undefined) ?? null,
    config: (body["config"] as Record<string, unknown> | undefined) ?? {},
  };

  try {
    const resp = await enterInvocation(agentRequest.invocationId, () =>
      agent.handle(agentRequest, ctx),
    );
    return respondJson(res, 200, serialiseResponse(resp));
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(`[konstera-sdk] agent.handle failed for ${agentRequest.invocationId}:`, err);
    return respondJson(res, 500, {
      error: {
        type: err instanceof Error ? err.name : "Error",
        message: err instanceof Error ? err.message : String(err),
      },
    });
  }
}

function serialiseResponse(resp: AgentResponse): Record<string, unknown> {
  return {
    content: resp.content,
    structured: resp.structured ?? null,
    toolCalls: resp.toolCalls ?? [],
  };
}

async function readJsonBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(chunk as Buffer);
  }
  const text = Buffer.concat(chunks).toString("utf8");
  if (!text) return {};
  return JSON.parse(text) as Record<string, unknown>;
}

function respondJson(res: ServerResponse, status: number, body: unknown): void {
  res.statusCode = status;
  res.setHeader("content-type", "application/json");
  res.end(JSON.stringify(body));
}

function listen(server: Server, port: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const onError = (err: Error): void => {
      server.off("listening", onListening);
      reject(err);
    };
    const onListening = (): void => {
      server.off("error", onError);
      resolve();
    };
    server.once("error", onError);
    server.once("listening", onListening);
    server.listen(port, "0.0.0.0");
  });
}
