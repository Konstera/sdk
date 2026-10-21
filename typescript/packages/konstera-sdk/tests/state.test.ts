/**
 * Tests for StateService — covers call shape + direct-run semantics.
 */
import { describe, expect, test, vi } from "vitest";
import { KernelMcpClient } from "../src/mcp.js";
import { StateService } from "../src/services/state.js";

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

describe("StateService.get", () => {
  test("sends state_get with instanceId + key", async () => {
    const { client, calls } = mockClient('"hello"');
    const state = new StateService(client, "inst-1");

    const result = await state.get("greeting");

    expect(result).toBe("hello");
    expect(calls[0]).toEqual({
      name: "state_get",
      args: { instanceId: "inst-1", key: "greeting" },
    });
  });

  test("returns null for missing key (kernel null)", async () => {
    const { client } = mockClient("null");
    const state = new StateService(client, "inst-1");
    expect(await state.get("missing")).toBeNull();
  });

  test("decodes structured JSON values", async () => {
    const payload = { user: 42, items: [1, 2, 3] };
    const { client } = mockClient(JSON.stringify(payload));
    const state = new StateService(client, "inst-1");

    const result = await state.get<typeof payload>("profile");

    expect(result).toEqual(payload);
  });

  test("direct-run mode returns null", async () => {
    const client = new KernelMcpClient(undefined);
    const state = new StateService(client, "inst-1");
    expect(await state.get("x")).toBeNull();
  });
});

describe("StateService.set", () => {
  test("serialises value to JSON", async () => {
    const { client, calls } = mockClient();
    const state = new StateService(client, "inst-1");

    await state.set("profile", { name: "Alice", age: 30 });

    expect(calls[0]).toEqual({
      name: "state_set",
      args: {
        instanceId: "inst-1",
        key: "profile",
        valueJson: JSON.stringify({ name: "Alice", age: 30 }),
      },
    });
  });

  test("serialises primitives", async () => {
    const { client, calls } = mockClient();
    const state = new StateService(client, "inst-1");

    await state.set("count", 42);
    await state.set("flag", true);
    await state.set("name", "Bob");

    const values = calls.map((c) => JSON.parse(c.args["valueJson"] as string));
    expect(values).toEqual([42, true, "Bob"]);
  });
});

describe("StateService.delete", () => {
  test("sends state_delete with instanceId + key", async () => {
    const { client, calls } = mockClient();
    const state = new StateService(client, "inst-1");

    await state.delete("some-key");

    expect(calls[0]).toEqual({
      name: "state_delete",
      args: { instanceId: "inst-1", key: "some-key" },
    });
  });
});

describe("StateService.list", () => {
  test("sends state_list with empty prefix by default", async () => {
    const { client, calls } = mockClient('["a", "b", "c"]');
    const state = new StateService(client, "inst-1");

    const keys = await state.list();

    expect(keys).toEqual(["a", "b", "c"]);
    expect(calls[0]).toEqual({
      name: "state_list",
      args: { instanceId: "inst-1", prefix: "" },
    });
  });

  test("respects prefix filter", async () => {
    const { client, calls } = mockClient('["user:1", "user:2"]');
    const state = new StateService(client, "inst-1");

    const keys = await state.list("user:");

    expect(keys).toEqual(["user:1", "user:2"]);
    expect(calls[0]?.args["prefix"]).toBe("user:");
  });

  test("returns empty array for empty/malformed response", async () => {
    const { client } = mockClient("");
    const state = new StateService(client, "inst-1");
    expect(await state.list()).toEqual([]);
  });

  test("direct-run returns empty array", async () => {
    const client = new KernelMcpClient(undefined);
    const state = new StateService(client, "inst-1");
    expect(await state.list()).toEqual([]);
  });
});
