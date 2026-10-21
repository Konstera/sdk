/**
 * AgentContext — the object passed to every agent method. Gives the agent access
 * to identity + kernel services without coupling to how those services are wired.
 *
 * v0.2.0: log + llm + state + vector + credentials. Other 10 services (cost,
 * tool, agents, artifact, human, rule, connector, capability, context,
 * semantic) ship in subsequent minor versions as parity with Python.
 */
import { KernelMcpClient } from "./mcp.js";
import { CredentialsService } from "./services/credentials.js";
import { LlmService } from "./services/llm.js";
import { LogService } from "./services/log.js";
import { StateService } from "./services/state.js";
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
  };
}
