/**
 * AgentContext — the object passed to every agent method. Gives the agent access
 * to identity + kernel services without coupling to how those services are wired.
 *
 * v0.3.0: full Python parity — 14 services (log, llm, state, vector, credentials,
 * cost, tool, agents, artifact, human, rule, connector, capability, semantic).
 * v0.5.0: + browser (kernel-hosted browser sessions).
 */
import { KernelMcpClient } from "./mcp.js";
import { AgentsService } from "./services/agents.js";
import { ArtifactService } from "./services/artifact.js";
import { BrowserService } from "./services/browser.js";
import { CapabilityService } from "./services/capability.js";
import { ConnectorService } from "./services/connector.js";
import { CostService } from "./services/cost.js";
import { CredentialsService } from "./services/credentials.js";
import { HumanService } from "./services/human.js";
import { LlmService } from "./services/llm.js";
import { LogService } from "./services/log.js";
import { RuleService } from "./services/rule.js";
import { SemanticService } from "./services/semantic.js";
import { StateService } from "./services/state.js";
import { ToolService } from "./services/tool.js";
import { VectorService } from "./services/vector.js";

export interface AgentContext {
  /** This agent instance's UUID (as string). Injected by the kernel. */
  readonly instanceId: string;

  /**
   * The tenant this instance runs under (M8). UUID as string. Injected by the
   * kernel at container-create time via KONSTERA_TENANT_ID.
   */
  readonly tenantId: string;

  /** The agent's declared id from its manifest. */
  readonly agentId: string;

  /** The agent's declared version. */
  readonly agentVersion: string;

  readonly log: LogService;
  readonly llm: LlmService;
  readonly state: StateService;
  readonly vector: VectorService;
  readonly credentials: CredentialsService;
  readonly cost: CostService;
  readonly tool: ToolService;
  readonly agents: AgentsService;
  readonly artifact: ArtifactService;
  readonly human: HumanService;
  readonly rule: RuleService;
  readonly connector: ConnectorService;
  readonly capability: CapabilityService;
  readonly semantic: SemanticService;
  /** Kernel-hosted browser sessions over a granted connection (v0.5.0). */
  readonly browser: BrowserService;
}

export interface AgentContextDefaults {
  instanceId?: string;
  tenantId?: string;
  agentId?: string;
  agentVersion?: string;
}

/**
 * Build an AgentContext from env vars the kernel injects at container-create
 * time. Missing values fall back to unknowns rather than raising — an agent
 * should be able to boot in direct-run mode with nothing set, and only
 * kernel-callback features degrade.
 */
export function createContext(
  mcp: KernelMcpClient,
  defaults: AgentContextDefaults = {},
): AgentContext {
  const instanceId =
    process.env["KONSTERA_AGENT_INSTANCE_ID"] ?? defaults.instanceId ?? "unknown-instance";
  const tenantId =
    process.env["KONSTERA_TENANT_ID"] ??
    defaults.tenantId ??
    "00000000-0000-0000-0000-000000000000";
  const agentId = process.env["KONSTERA_AGENT_ID"] ?? defaults.agentId ?? "unknown-agent";
  const agentVersion =
    process.env["KONSTERA_AGENT_VERSION"] ?? defaults.agentVersion ?? "0.0.0";

  return {
    instanceId,
    tenantId,
    agentId,
    agentVersion,
    log: new LogService(mcp, instanceId),
    llm: new LlmService(mcp, instanceId),
    state: new StateService(mcp, instanceId),
    vector: new VectorService(mcp, instanceId),
    credentials: new CredentialsService(mcp, instanceId),
    cost: new CostService(mcp, instanceId),
    tool: new ToolService(mcp),
    agents: new AgentsService(mcp, instanceId),
    artifact: new ArtifactService(mcp, instanceId),
    human: new HumanService(mcp, instanceId),
    rule: new RuleService(mcp, instanceId),
    connector: new ConnectorService(mcp, instanceId),
    capability: new CapabilityService(mcp, instanceId),
    semantic: new SemanticService(mcp, instanceId),
    browser: new BrowserService(mcp, instanceId),
  };
}
