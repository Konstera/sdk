/**
 * @konstera/sdk — TypeScript SDK for Konstera agents.
 *
 * Build an agent in ~10 lines:
 *
 *   import { Agent, AgentContext, AgentRequest, AgentResponse, run } from "@konstera/sdk";
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

// Core services
export { LogService } from "./services/log.js";
export { LlmService } from "./services/llm.js";
export type { LlmResult, LlmUsage, LlmCompleteOptions } from "./services/llm.js";
export { StateService } from "./services/state.js";
export { VectorService } from "./services/vector.js";
export type { VectorHit, VectorUpsertOptions, VectorQueryOptions } from "./services/vector.js";
export { CredentialsService } from "./services/credentials.js";

// v0.3.0 — full Python parity
export { CostService } from "./services/cost.js";
export type { CostRecordOptions } from "./services/cost.js";
export { ToolService } from "./services/tool.js";
export type { ToolDescriptor } from "./services/tool.js";
export { AgentsService } from "./services/agents.js";
export type { AgentInvokeResult, AgentInvokeOptions } from "./services/agents.js";
export { ArtifactService } from "./services/artifact.js";
export type {
  PutResult,
  GetResult,
  HeadResult,
  ArtifactListItem,
  PutOptions,
} from "./services/artifact.js";
export { HumanService, isResolved, isApproved } from "./services/human.js";
export type {
  Tier,
  Status,
  Decision,
  HumanDecision,
  HumanRequestOptions,
} from "./services/human.js";
export { RuleService } from "./services/rule.js";
export type { Rule, RuleSummary } from "./services/rule.js";
export { ConnectorService } from "./services/connector.js";
export type { ConnectorGrant } from "./services/connector.js";
export {
  CapabilityService,
  CapabilityError,
  CapabilityUnbound,
  CapabilityUpstreamFailed,
} from "./services/capability.js";
export { SemanticService } from "./services/semantic.js";
export type {
  GlossaryTerm,
  OntologyEntity,
  Skill,
  SkillStep,
  ClusterPassRate,
} from "./services/semantic.js";

// v0.5.0 — browser sessions + categorised failures (Python 0.7.0 parity)
export { BrowserService, BrowserSession } from "./services/browser.js";
export type {
  BrowserConnection,
  BrowserWaitUntil,
  NavigateResult,
  WaitForResult,
  ExistsResult,
  HandoffResult,
  ExtractField,
  ExtractRow,
  TimeoutOptions,
  WaitForOptions,
  HandoffOptions,
} from "./services/browser.js";
export { AgentFailure } from "./types.js";
export type {
  AgentRequest,
  AgentResponse,
  AgentFailureCategory,
  AgentFailureOptions,
} from "./types.js";

// Keep in step with package.json "version"; sdk-check fails the build if they differ.
export const VERSION = "0.5.0";
