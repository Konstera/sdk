/**
 * Shape tests for the 9 services added in v0.3.0.
 *
 * One happy-path test per method per service, plus direct-run no-op semantics.
 * Comprehensive edge-case coverage is deferred — this file proves the services
 * are wired correctly and respect the direct-run contract.
 */
import { describe, expect, test, vi } from "vitest";
import { KernelMcpClient } from "../src/mcp.js";
import { AgentsService } from "../src/services/agents.js";
import { ArtifactService } from "../src/services/artifact.js";
import {
  CapabilityError,
  CapabilityService,
  CapabilityUnbound,
  CapabilityUpstreamFailed,
} from "../src/services/capability.js";
import { ConnectorService } from "../src/services/connector.js";
import { CostService } from "../src/services/cost.js";
import { HumanService, isApproved, isResolved } from "../src/services/human.js";
import { RuleService } from "../src/services/rule.js";
import { SemanticService } from "../src/services/semantic.js";
import { ToolService } from "../src/services/tool.js";

function mock(response: string | null = null) {
  const calls: Array<{ name: string; args: Record<string, unknown> }> = [];
  const client = new KernelMcpClient("http://mock");
  vi.spyOn(client, "callTool").mockImplementation(async (name, args) => {
    calls.push({ name, args });
    return {
      disabled: false,
      content: response === null ? [] : [{ type: "text", text: response }],
    };
  });
  return { client, calls };
}

describe("CostService", () => {
  test("record sends instance + kind + cost (minimal)", async () => {
    const { client, calls } = mock();
    const cost = new CostService(client, "inst-1");
    await cost.record({ kind: "tool", costUsd: 0.01 });
    expect(calls[0]).toEqual({
      name: "cost_record",
      args: { instanceId: "inst-1", kind: "tool", costUsd: 0.01 },
    });
  });

  test("record includes all optional fields", async () => {
    const { client, calls } = mock();
    const cost = new CostService(client, "inst-1");
    await cost.record({
      kind: "llm",
      costUsd: 0.001,
      model: "x",
      inputTokens: 10,
      outputTokens: 5,
      metadata: { k: "v" },
    });
    const args = calls[0]!.args;
    expect(args["modelId"]).toBe("x");
    expect(args["inputTokens"]).toBe(10);
    expect(args["outputTokens"]).toBe(5);
    expect(JSON.parse(args["metadataJson"] as string)).toEqual({ k: "v" });
  });
});

describe("ToolService", () => {
  test("list returns tools", async () => {
    const { client } = mock(JSON.stringify([{ name: "datetime_now", description: "UTC" }]));
    const tool = new ToolService(client);
    const tools = await tool.list();
    expect(tools).toHaveLength(1);
    expect(tools[0]?.name).toBe("datetime_now");
  });

  test("call serialises args + returns decoded JSON", async () => {
    const { client, calls } = mock('"2026-10-21T12:00:00Z"');
    const tool = new ToolService(client);
    const result = await tool.call("datetime_now", { tz: "UTC" });
    expect(result).toBe("2026-10-21T12:00:00Z");
    expect(JSON.parse(calls[0]!.args["argsJson"] as string)).toEqual({ tz: "UTC" });
  });

  test("direct-run returns [] / null", async () => {
    const client = new KernelMcpClient(undefined);
    const tool = new ToolService(client);
    expect(await tool.list()).toEqual([]);
    expect(await tool.call("x")).toBeNull();
  });
});

describe("AgentsService", () => {
  test("invoke returns typed result", async () => {
    const { client } = mock(
      JSON.stringify({
        content: "hello",
        structured: { x: 1 },
        toolCalls: [{ fn: "y" }],
      }),
    );
    const agents = new AgentsService(client, "inst-1");
    const result = await agents.invoke("other-agent", { input: "hi" });
    expect(result.content).toBe("hello");
    expect(result.structured).toEqual({ x: 1 });
    expect(result.toolCalls).toEqual([{ fn: "y" }]);
  });

  test("invoke serialises payload + config", async () => {
    const { client, calls } = mock('{"content":""}');
    const agents = new AgentsService(client, "inst-1");
    await agents.invoke("other", {
      input: "x",
      payload: { a: 1 },
      config: { b: 2 },
    });
    expect(JSON.parse(calls[0]!.args["payloadJson"] as string)).toEqual({ a: 1 });
    expect(JSON.parse(calls[0]!.args["configJson"] as string)).toEqual({ b: 2 });
  });
});

describe("CapabilityService", () => {
  test("available returns true for {available:true}", async () => {
    const { client } = mock('{"available": true}');
    const cap = new CapabilityService(client, "inst-1");
    expect(await cap.available("orders.lookup_by_email")).toBe(true);
  });

  test("available returns false for malformed response", async () => {
    const { client } = mock("not-json");
    const cap = new CapabilityService(client, "inst-1");
    expect(await cap.available("x")).toBe(false);
  });

  test("call maps [Unbound] prefix to CapabilityUnbound", async () => {
    const client = new KernelMcpClient("http://mock");
    vi.spyOn(client, "callTool").mockRejectedValue(
      new Error("[Unbound] Agent has no binding for orders.lookup_by_id"),
    );
    const cap = new CapabilityService(client, "inst-1");
    await expect(cap.call("orders.lookup_by_id")).rejects.toBeInstanceOf(CapabilityUnbound);
  });

  test("call maps [UpstreamFailed] prefix to CapabilityUpstreamFailed", async () => {
    const client = new KernelMcpClient("http://mock");
    vi.spyOn(client, "callTool").mockRejectedValue(
      new Error("[UpstreamFailed] Shopify POST /orders failed (500)"),
    );
    const cap = new CapabilityService(client, "inst-1");
    await expect(cap.call("x")).rejects.toBeInstanceOf(CapabilityUpstreamFailed);
  });

  test("call falls back to CapabilityError for unknown prefix", async () => {
    const client = new KernelMcpClient("http://mock");
    vi.spyOn(client, "callTool").mockRejectedValue(new Error("Some other failure"));
    const cap = new CapabilityService(client, "inst-1");
    await expect(cap.call("x")).rejects.toBeInstanceOf(CapabilityError);
  });
});

describe("ConnectorService", () => {
  test("list returns typed grants", async () => {
    const grants = [
      { alias: "shopify_uk", connectorTypeKey: "shopify", connectionId: "c-1", scope: { s: 1 } },
    ];
    const { client } = mock(JSON.stringify(grants));
    const conn = new ConnectorService(client, "inst-1");
    const result = await conn.list();
    expect(result[0]?.alias).toBe("shopify_uk");
    expect(result[0]?.scope).toEqual({ s: 1 });
  });

  test("call serialises alias + method + args", async () => {
    const { client, calls } = mock('{"rows":[]}');
    const conn = new ConnectorService(client, "inst-1");
    await conn.call("pg", "query", { sql: "SELECT 1" });
    expect(calls[0]!.args["alias"]).toBe("pg");
    expect(calls[0]!.args["method"]).toBe("query");
    expect(JSON.parse(calls[0]!.args["argsJson"] as string)).toEqual({ sql: "SELECT 1" });
  });
});

describe("RuleService", () => {
  const rulePayload = {
    ruleId: "r-1",
    ruleKey: "prepayment",
    version: 2,
    effectiveFrom: "2026-01-01",
    content: { threshold_usd: 5000 },
    description: "test",
    proposedBy: "u",
    proposedRole: "ctrl",
    proposedAt: "2025-12-01",
    approvedBy: "u2",
    approvedRole: "cfo",
    approvedAt: "2025-12-15",
    decisionReason: "ok",
  };

  test("get returns typed Rule", async () => {
    const { client } = mock(JSON.stringify(rulePayload));
    const rule = new RuleService(client, "inst-1");
    const r = await rule.get("prepayment");
    expect(r?.ruleId).toBe("r-1");
    expect(r?.version).toBe(2);
    expect(r?.content).toEqual({ threshold_usd: 5000 });
  });

  test("list with ruleKey returns Rule[]", async () => {
    const { client } = mock(JSON.stringify([rulePayload, { ...rulePayload, version: 3 }]));
    const rule = new RuleService(client, "inst-1");
    const list = (await rule.list("prepayment")) as { version: number }[];
    expect(list).toHaveLength(2);
    expect(list[0]!.version).toBe(2);
  });

  test("list without ruleKey returns summaries", async () => {
    const summaries = [
      { ruleKey: "a", ruleId: "r-a", version: 1, effectiveFrom: "t", description: null },
    ];
    const { client } = mock(JSON.stringify(summaries));
    const rule = new RuleService(client, "inst-1");
    const list = await rule.list();
    expect(list).toHaveLength(1);
    expect((list[0] as { ruleKey: string }).ruleKey).toBe("a");
  });
});

describe("ArtifactService", () => {
  test("put encodes bytes to base64 + returns PutResult", async () => {
    const { client, calls } = mock(
      JSON.stringify({
        artifactId: "a-1",
        sha256: "h",
        sizeBytes: 5,
        contentType: "text/plain",
        storageUri: "minio://b/h",
        dedup: false,
      }),
    );
    const art = new ArtifactService(client, "inst-1");
    const result = await art.put({
      content: new TextEncoder().encode("hello"),
      contentType: "text/plain",
    });
    expect(result.artifactId).toBe("a-1");
    expect(calls[0]!.args["contentBase64"]).toBe("aGVsbG8="); // base64 of "hello"
  });

  test("get decodes base64 back to bytes", async () => {
    const bytes = new TextEncoder().encode("the quick brown fox");
    const payload = {
      contentBase64: Buffer.from(bytes).toString("base64"),
      contentType: "text/plain",
      sizeBytes: bytes.length,
      sha256: "h",
    };
    const { client } = mock(JSON.stringify(payload));
    const art = new ArtifactService(client, "inst-1");
    const result = await art.get("h");
    expect(new TextDecoder().decode(result.content)).toBe("the quick brown fox");
  });

  test("head exists:false returns HeadResult with nulls", async () => {
    const { client } = mock(JSON.stringify({ exists: false, sha256: "missing" }));
    const art = new ArtifactService(client, "inst-1");
    const h = await art.head("missing");
    expect(h.exists).toBe(false);
    expect(h.sizeBytes).toBeNull();
    expect(h.contentType).toBeNull();
  });
});

describe("HumanService", () => {
  const decisionPayload = {
    approvalId: "a-1",
    kind: "k",
    tier: "T1",
    status: "pending",
    summary: "s",
    submitterInstanceId: "inst-1",
    options: ["approve", "reject"],
    submittedAt: "2026-10-21",
    detail: { x: 1 },
  };

  test("request returns typed HumanDecision", async () => {
    const { client } = mock(JSON.stringify(decisionPayload));
    const human = new HumanService(client, "inst-1");
    const d = await human.request({ kind: "k", tier: "T1", summary: "s" });
    expect(d.approvalId).toBe("a-1");
    expect(d.tier).toBe("T1");
    expect(d.detail).toEqual({ x: 1 });
  });

  test("isResolved + isApproved reflect status", () => {
    expect(isResolved({ ...decisionPayload, status: "pending" } as never)).toBe(false);
    expect(isResolved({ ...decisionPayload, status: "approved" } as never)).toBe(true);
    expect(isApproved({ ...decisionPayload, status: "approved" } as never)).toBe(true);
    expect(isApproved({ ...decisionPayload, status: "rejected" } as never)).toBe(false);
  });

  test("waitSeconds triggers second call when pending", async () => {
    const client = new KernelMcpClient("http://mock");
    let callCount = 0;
    vi.spyOn(client, "callTool").mockImplementation(async () => {
      callCount++;
      const status = callCount === 1 ? "pending" : "approved";
      return {
        disabled: false,
        content: [
          { type: "text", text: JSON.stringify({ ...decisionPayload, status }) },
        ],
      };
    });
    const human = new HumanService(client, "inst-1");
    const d = await human.request({ kind: "k", tier: "T1", summary: "s", waitSeconds: 10 });
    expect(d.status).toBe("approved");
    expect(callCount).toBe(2); // submit + wait
  });
});

describe("SemanticService", () => {
  test("glossaryLookup returns typed term", async () => {
    const { client } = mock(
      JSON.stringify({
        id: "t-1",
        name: "refund_window_days",
        definition: "30-day window",
        synonyms: ["refund_days"],
        canonical_unit: "days",
        version: 1,
        status: "active",
        repository_id: "r",
        repository_name: "cs",
        updated_at: "2026-10-20",
      }),
    );
    const sem = new SemanticService(client, "inst-1");
    const term = await sem.glossaryLookup("refund_window_days");
    expect(term?.name).toBe("refund_window_days");
    expect(term?.canonicalUnit).toBe("days");
  });

  test("ontologyLookup parses properties JSON string", async () => {
    const props = { identity: { primary: { field: "email" } } };
    const { client } = mock(
      JSON.stringify({
        id: "e-1",
        canonical_name: "customer",
        entity_type: "person",
        properties: JSON.stringify(props),
        repository_id: "r",
        repository_name: "retail",
        updated_at: "x",
      }),
    );
    const sem = new SemanticService(client, "inst-1");
    const entity = await sem.ontologyLookup("customer");
    expect(entity?.properties).toEqual(props);
  });

  test("feature_disabled envelope → null/empty", async () => {
    const { client } = mock(JSON.stringify({ status: "feature_disabled" }));
    const sem = new SemanticService(client, "inst-1");
    expect(await sem.glossaryLookup("x")).toBeNull();
    expect(await sem.glossaryList()).toEqual([]);
    expect(await sem.ontologyLookup("x")).toBeNull();
    expect(await sem.skillsGet("x")).toBeNull();
  });

  test("clusterPassRate wraps clusterPassRates", async () => {
    const { client } = mock(
      JSON.stringify({
        "refund-eligible": {
          cluster_tag: "refund-eligible",
          total: 20,
          passed: 17,
          pass_rate: 0.85,
          run_id: "r-1",
          recorded_at: "x",
        },
      }),
    );
    const sem = new SemanticService(client, "inst-1");
    const rate = await sem.clusterPassRate("agent-id", "refund-eligible");
    expect(rate?.passRate).toBe(0.85);
  });
});
