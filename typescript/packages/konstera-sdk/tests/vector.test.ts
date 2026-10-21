/**
 * Tests for VectorService — upsert, query, delete.
 */
import { describe, expect, test, vi } from "vitest";
import { KernelMcpClient } from "../src/mcp.js";
import { VectorService } from "../src/services/vector.js";

function mockClient(response: string | null = null): {
  client: KernelMcpClient;
  calls: Array<{ name: string; args: Record<string, unknown> }>;
} {
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

describe("VectorService.upsert", () => {
  test("returns chunkId from kernel response", async () => {
    const { client } = mockClient(JSON.stringify({ chunkId: "chunk-abc" }));
    const vector = new VectorService(client, "inst-1");

    const id = await vector.upsert({
      namespace: "agent:inst-1",
      content: "hello world",
    });

    expect(id).toBe("chunk-abc");
  });

  test("sends callerInstanceId + namespace + content", async () => {
    const { client, calls } = mockClient('{"chunkId":"x"}');
    const vector = new VectorService(client, "inst-1");

    await vector.upsert({
      namespace: "shared:kb",
      content: "the quick brown fox",
    });

    expect(calls[0]).toEqual({
      name: "vector_upsert",
      args: {
        callerInstanceId: "inst-1",
        namespace: "shared:kb",
        content: "the quick brown fox",
      },
    });
  });

  test("passes external_id + metadata when provided", async () => {
    const { client, calls } = mockClient('{"chunkId":"x"}');
    const vector = new VectorService(client, "inst-1");

    await vector.upsert({
      namespace: "shared:kb",
      content: "content",
      externalId: "doc-42",
      metadata: { source: "docs", page: 7 },
    });

    const args = calls[0]!.args as Record<string, unknown>;
    expect(args["externalId"]).toBe("doc-42");
    expect(JSON.parse(args["metadataJson"] as string)).toEqual({
      source: "docs",
      page: 7,
    });
  });

  test("omits externalId + metadata when not provided", async () => {
    const { client, calls } = mockClient('{"chunkId":"x"}');
    const vector = new VectorService(client, "inst-1");

    await vector.upsert({ namespace: "shared:kb", content: "x" });

    const args = calls[0]!.args as Record<string, unknown>;
    expect(args).not.toHaveProperty("externalId");
    expect(args).not.toHaveProperty("metadataJson");
  });

  test("direct-run returns empty string", async () => {
    const client = new KernelMcpClient(undefined);
    const vector = new VectorService(client, "inst-1");
    expect(await vector.upsert({ namespace: "x", content: "y" })).toBe("");
  });
});

describe("VectorService.query", () => {
  test("returns typed hits", async () => {
    const hits = [
      {
        id: "c-1",
        externalId: "doc-1",
        content: "snippet one",
        metadata: { source: "docs" },
        score: 0.92,
      },
      {
        id: "c-2",
        externalId: null,
        content: "snippet two",
        metadata: {},
        score: 0.85,
      },
    ];
    const { client } = mockClient(JSON.stringify(hits));
    const vector = new VectorService(client, "inst-1");

    const result = await vector.query({
      namespace: "shared:kb",
      queryText: "refund policy",
    });

    expect(result).toHaveLength(2);
    expect(result[0]?.id).toBe("c-1");
    expect(result[0]?.externalId).toBe("doc-1");
    expect(result[0]?.score).toBe(0.92);
    expect(result[1]?.externalId).toBeNull();
  });

  test("defaults topK to 5", async () => {
    const { client, calls } = mockClient("[]");
    const vector = new VectorService(client, "inst-1");

    await vector.query({ namespace: "x", queryText: "y" });

    expect(calls[0]!.args["topK"]).toBe(5);
  });

  test("respects custom topK", async () => {
    const { client, calls } = mockClient("[]");
    const vector = new VectorService(client, "inst-1");

    await vector.query({ namespace: "x", queryText: "y", topK: 20 });

    expect(calls[0]!.args["topK"]).toBe(20);
  });

  test("tolerates missing fields in hit", async () => {
    const { client } = mockClient(JSON.stringify([{ id: "c-x", content: "x" }]));
    const vector = new VectorService(client, "inst-1");

    const result = await vector.query({ namespace: "x", queryText: "y" });

    expect(result[0]?.externalId).toBeNull();
    expect(result[0]?.metadata).toEqual({});
    expect(result[0]?.score).toBe(0);
  });

  test("direct-run returns empty array", async () => {
    const client = new KernelMcpClient(undefined);
    const vector = new VectorService(client, "inst-1");
    expect(
      await vector.query({ namespace: "x", queryText: "y" }),
    ).toEqual([]);
  });
});

describe("VectorService.delete", () => {
  test("sends namespace + externalId", async () => {
    const { client, calls } = mockClient();
    const vector = new VectorService(client, "inst-1");

    await vector.delete("shared:kb", "doc-42");

    expect(calls[0]).toEqual({
      name: "vector_delete",
      args: {
        callerInstanceId: "inst-1",
        namespace: "shared:kb",
        externalId: "doc-42",
      },
    });
  });
});
