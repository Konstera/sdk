/**
 * SemanticService — tenant semantic plane access (ADR-037).
 * Mirror of Python's semantic.py.
 *
 * Exposes glossary + ontology + skills + cluster eval signals. All methods
 * return null/[]/{} when the Context Service feature is disabled for the
 * tenant (ADR-039), so agents branch on data availability rather than
 * special-casing feature-disabled.
 */
import type { KernelMcpClient } from "../mcp.js";

export interface GlossaryTerm {
  readonly id: string;
  readonly name: string;
  readonly definition: string;
  readonly synonyms: string[];
  readonly canonicalUnit: string | null;
  readonly ownerUserId: string | null;
  readonly version: number;
  readonly status: string;
  readonly repositoryId: string;
  readonly repositoryName: string;
  readonly updatedAt: string;
}

export interface OntologyEntity {
  readonly id: string;
  readonly canonicalName: string;
  readonly entityType: string;
  readonly synonyms: string[];
  readonly description: string | null;
  readonly repositoryId: string;
  readonly repositoryName: string;
  readonly properties: Record<string, unknown>;
  readonly source: string;
  readonly status: string;
  readonly updatedAt: string;
}

export interface SkillStep {
  readonly stepOrder: number;
  readonly kind: string;
  readonly description: string | null;
  readonly payload: Record<string, unknown>;
}

export interface Skill {
  readonly id: string;
  readonly name: string;
  readonly description: string | null;
  readonly domain: string;
  readonly agentBindingMask: string[];
  readonly version: number;
  readonly status: string;
  readonly repositoryId: string;
  readonly repositoryName: string;
  readonly steps: SkillStep[];
}

export interface ClusterPassRate {
  readonly clusterTag: string;
  readonly total: number;
  readonly passed: number;
  readonly passRate: number;
  readonly runId: string;
  readonly recordedAt: string;
}

export class SemanticService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /** Look up a glossary term. */
  async glossaryLookup(term: string): Promise<GlossaryTerm | null> {
    const result = await this.mcp.callTool("context_glossary_lookup", {
      callerInstanceId: this.instanceId,
      term,
    });
    if (result.disabled) return null;
    const text = extractText(result.content);
    if (!text || text === "null") return null;
    const data = JSON.parse(text) as unknown;
    if (isFeatureDisabled(data)) return null;
    return parseGlossaryTerm(data as Record<string, unknown>);
  }

  /**
   * Look up a glossary term by its stable record ID.
   *
   * Use this for deterministic replay of past invocations: when the agent
   * records a term's ID (not name) in its output, a later replay resolves
   * the same record even if the term has since been renamed or edited.
   *
   * Requires platform support for the `context_glossary_lookup_by_id` MCP
   * tool. Returns null gracefully if the kernel doesn't yet expose it.
   */
  async glossaryLookupById(id: string): Promise<GlossaryTerm | null> {
    const result = await this.mcp.callTool("context_glossary_lookup_by_id", {
      callerInstanceId: this.instanceId,
      id,
    });
    if (result.disabled) return null;
    const text = extractText(result.content);
    if (!text || text === "null") return null;
    const data = JSON.parse(text) as unknown;
    if (isFeatureDisabled(data)) return null;
    return parseGlossaryTerm(data as Record<string, unknown>);
  }

  /** List active glossary terms, optionally filtered by domain. */
  async glossaryList(domain?: string): Promise<GlossaryTerm[]> {
    const args: Record<string, unknown> = { callerInstanceId: this.instanceId };
    if (domain !== undefined) args["domain"] = domain;
    const result = await this.mcp.callTool("context_glossary_list", args);
    if (result.disabled) return [];
    const text = extractText(result.content);
    if (!text) return [];
    const data = JSON.parse(text) as unknown;
    if (isFeatureDisabled(data)) return [];
    if (!Array.isArray(data)) return [];
    return data.map((d) => parseGlossaryTerm(d as Record<string, unknown>));
  }

  /** Look up a business entity from the tenant ontology. */
  async ontologyLookup(entityName: string): Promise<OntologyEntity | null> {
    const result = await this.mcp.callTool("context_ontology_resolve", {
      callerInstanceId: this.instanceId,
      entityName,
    });
    if (result.disabled) return null;
    const text = extractText(result.content);
    if (!text || text === "null") return null;
    const data = JSON.parse(text) as unknown;
    if (isFeatureDisabled(data)) return null;
    return parseOntologyEntity(data as Record<string, unknown>);
  }

  /** Fetch a skill with its ordered steps. */
  async skillsGet(name: string): Promise<Skill | null> {
    const result = await this.mcp.callTool("context_skills_get", {
      callerInstanceId: this.instanceId,
      skillName: name,
    });
    if (result.disabled) return null;
    const text = extractText(result.content);
    if (!text || text === "null") return null;
    const data = JSON.parse(text) as unknown;
    if (isFeatureDisabled(data)) return null;
    return parseSkill(data as Record<string, unknown>);
  }

  /** Fetch per-cluster pass rates for an agent (ADR-037 W3-B). */
  async clusterPassRates(agentId: string): Promise<Record<string, ClusterPassRate>> {
    const result = await this.mcp.callTool("context_evaluation_cluster_pass_rates", {
      callerInstanceId: this.instanceId,
      agentId,
    });
    if (result.disabled) return {};
    const text = extractText(result.content);
    if (!text) return {};
    const data = JSON.parse(text) as unknown;
    if (isFeatureDisabled(data)) return {};
    if (typeof data !== "object" || data === null || Array.isArray(data)) return {};
    const result2: Record<string, ClusterPassRate> = {};
    for (const [k, v] of Object.entries(data)) {
      result2[k] = parseClusterPassRate(v as Record<string, unknown>);
    }
    return result2;
  }

  /** Fetch one cluster's pass rate. Thin wrapper over clusterPassRates. */
  async clusterPassRate(
    agentId: string,
    clusterTag: string,
  ): Promise<ClusterPassRate | null> {
    const map = await this.clusterPassRates(agentId);
    return map[clusterTag] ?? null;
  }
}

function parseGlossaryTerm(d: Record<string, unknown>): GlossaryTerm {
  return {
    id: String(d["id"] ?? ""),
    name: String(d["name"] ?? ""),
    definition: String(d["definition"] ?? ""),
    synonyms: (d["synonyms"] as string[] | undefined) ?? [],
    canonicalUnit: (d["canonical_unit"] as string | null | undefined) ?? null,
    ownerUserId: (d["owner_user_id"] as string | null | undefined) ?? null,
    version: Number(d["version"] ?? 1),
    status: String(d["status"] ?? "active"),
    repositoryId: String(d["repository_id"] ?? ""),
    repositoryName: String(d["repository_name"] ?? ""),
    updatedAt: String(d["updated_at"] ?? ""),
  };
}

function parseOntologyEntity(d: Record<string, unknown>): OntologyEntity {
  let parsedProps: Record<string, unknown> = {};
  const rawProps = d["properties"];
  if (typeof rawProps === "string") {
    try {
      parsedProps = JSON.parse(rawProps) as Record<string, unknown>;
    } catch {
      parsedProps = {};
    }
  } else if (rawProps !== null && typeof rawProps === "object") {
    parsedProps = rawProps as Record<string, unknown>;
  }
  return {
    id: String(d["id"] ?? ""),
    canonicalName: String(d["canonical_name"] ?? ""),
    entityType: String(d["entity_type"] ?? ""),
    synonyms: (d["synonyms"] as string[] | undefined) ?? [],
    description: (d["description"] as string | null | undefined) ?? null,
    repositoryId: String(d["repository_id"] ?? ""),
    repositoryName: String(d["repository_name"] ?? ""),
    properties: parsedProps,
    source: String(d["source"] ?? "authored"),
    status: String(d["status"] ?? "active"),
    updatedAt: String(d["updated_at"] ?? ""),
  };
}

function parseSkill(d: Record<string, unknown>): Skill {
  const rawSteps = (d["steps"] as Array<Record<string, unknown>> | undefined) ?? [];
  return {
    id: String(d["id"] ?? ""),
    name: String(d["name"] ?? ""),
    description: (d["description"] as string | null | undefined) ?? null,
    domain: String(d["domain"] ?? "general"),
    agentBindingMask: (d["agent_binding_mask"] as string[] | undefined) ?? [],
    version: Number(d["version"] ?? 1),
    status: String(d["status"] ?? "active"),
    repositoryId: String(d["repository_id"] ?? ""),
    repositoryName: String(d["repository_name"] ?? ""),
    steps: rawSteps.map((s, i) => ({
      stepOrder: Number(s["step_order"] ?? i + 1),
      kind: String(s["kind"] ?? ""),
      description: (s["description"] as string | null | undefined) ?? null,
      payload: (s["payload"] as Record<string, unknown> | null | undefined) ?? {},
    })),
  };
}

function parseClusterPassRate(d: Record<string, unknown>): ClusterPassRate {
  return {
    clusterTag: String(d["cluster_tag"] ?? ""),
    total: Number(d["total"] ?? 0),
    passed: Number(d["passed"] ?? 0),
    passRate: Number(d["pass_rate"] ?? 0),
    runId: String(d["run_id"] ?? ""),
    recordedAt: String(d["recorded_at"] ?? ""),
  };
}

function isFeatureDisabled(data: unknown): boolean {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as Record<string, unknown>)["status"] === "feature_disabled"
  );
}

function extractText(content: Array<{ type: string; text?: string }>): string | null {
  const first = content[0];
  if (!first || first.type !== "text") return null;
  return first.text ?? null;
}
