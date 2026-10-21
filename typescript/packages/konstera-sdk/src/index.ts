/**
 * konstera-sdk — TypeScript SDK for Konstera agents.
 *
 * Build an agent in ~10 lines:
 *
 *   import { Agent, AgentContext, AgentRequest, AgentResponse, run } from "konstera-sdk";
 *
 *   class HelloAgent extends Agent {
 *     async handle(req: AgentRequest, ctx: AgentContext): Promise<AgentResponse> {
 *       await ctx.log.info(`Hello, ${req.input}!`);
 *       return { content: `Hello, ${req.input}!` };
 *     }
 *   }
 *
 *   run(new HelloAgent());
 */
export { Agent } from "./agent.js";
export type { AgentContext, AgentContextDefaults } from "./context.js";
export { createContext } from "./context.js";
export { KernelMcpClient } from "./mcp.js";
export type { KernelCallResult } from "./mcp.js";
export { run } from "./runtime.js";
export type { RunOptions } from "./runtime.js";
export { LogService } from "./services/log.js";
export { LlmService } from "./services/llm.js";
export type { LlmResult, LlmUsage, LlmCompleteOptions } from "./services/llm.js";
export type { AgentRequest, AgentResponse } from "./types.js";

export const VERSION = "0.1.0";
