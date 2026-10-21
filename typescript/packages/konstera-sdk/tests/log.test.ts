/**
 * Tests for LogService — verifies both kernel-connected call shape and
 * direct-run no-op behaviour. Does not reach a real kernel; uses a mock
 * KernelMcpClient so we can assert on the exact payload sent.
 */
import { describe, expect, test, vi } from "vitest";
import { enterInvocation } from "../src/invocation-context.js";
import { KernelMcpClient } from "../src/mcp.js";
import { LogService } from "../src/services/log.js";

function mockClient(): { client: KernelMcpClient; calls: Array<{ name: string; args: unknown }> } {
  const calls: Array<{ name: string; args: unknown }> = [];
  const client = new KernelMcpClient("http://mock");
  // Replace callTool with a spy. We bypass the real HTTP connect by
  // directly stubbing the method — the surface we care about is "what
  // did LogService send to the kernel?", not transport correctness.
  vi.spyOn(client, "callTool").mockImplementation(async (name, args) => {
    calls.push({ name, args });
    return { disabled: false, content: [] };
  });
  return { client, calls };
}

describe("LogService", () => {
  test("info sends log_info tool call with instance ID + message + empty fields", async () => {
    const { client, calls } = mockClient();
    const log = new LogService(client, "inst-1");

    await log.info("hello world");

    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual({
      name: "log_info",
      args: {
        callerInstanceId: "inst-1",
        message: "hello world",
        fields: "{}",
      },
    });
  });

  test("warn serialises structured fields to a JSON string", async () => {
    const { client, calls } = mockClient();
    const log = new LogService(client, "inst-1");

    await log.warn("slow query", { durationMs: 1234, query: "SELECT 1" });

    expect(calls[0]?.name).toBe("log_warn");
    const args = calls[0]?.args as { fields: string };
    expect(JSON.parse(args.fields)).toEqual({ durationMs: 1234, query: "SELECT 1" });
  });

  test("error payload includes invocationId when inside enterInvocation", async () => {
    const { client, calls } = mockClient();
    const log = new LogService(client, "inst-1");

    await enterInvocation("inv-xyz", async () => {
      await log.error("boom");
    });

    const args = calls[0]?.args as { invocationId?: string };
    expect(args.invocationId).toBe("inv-xyz");
  });

  test("payload omits invocationId when outside enterInvocation", async () => {
    const { client, calls } = mockClient();
    const log = new LogService(client, "inst-1");

    await log.info("outside scope");

    const args = calls[0]?.args as Record<string, unknown>;
    expect(args).not.toHaveProperty("invocationId");
  });

  test("direct-run mode (no URL): callTool returns disabled stub, LogService completes successfully", async () => {
    const client = new KernelMcpClient(undefined);
    const log = new LogService(client, "inst-1");

    // Should not throw — direct-run mode is a core SDK contract (agents must
    // boot and run unit tests without a live kernel).
    await expect(log.info("hello")).resolves.toBeUndefined();
    await expect(log.warn("hello")).resolves.toBeUndefined();
    await expect(log.error("hello")).resolves.toBeUndefined();
  });
});
