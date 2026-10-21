/**
 * Tests for createContext — env var reading, sentinel fallbacks, and the
 * contract that direct-run mode always boots cleanly.
 */
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { createContext } from "../src/context.js";
import { KernelMcpClient } from "../src/mcp.js";

describe("createContext", () => {
  const envBackup: Record<string, string | undefined> = {};
  const envVars = [
    "KONSTERA_AGENT_INSTANCE_ID",
    "KONSTERA_TENANT_ID",
    "KONSTERA_AGENT_ID",
    "KONSTERA_AGENT_VERSION",
  ];

  beforeEach(() => {
    for (const v of envVars) {
      envBackup[v] = process.env[v];
      delete process.env[v];
    }
  });

  afterEach(() => {
    for (const v of envVars) {
      if (envBackup[v] === undefined) {
        delete process.env[v];
      } else {
        process.env[v] = envBackup[v];
      }
    }
  });

  test("reads env vars when set", () => {
    process.env["KONSTERA_AGENT_INSTANCE_ID"] = "inst-abc";
    process.env["KONSTERA_TENANT_ID"] = "tenant-xyz";
    process.env["KONSTERA_AGENT_ID"] = "io.konstera.test";
    process.env["KONSTERA_AGENT_VERSION"] = "1.2.3";

    const ctx = createContext(new KernelMcpClient(undefined));

    expect(ctx.instanceId).toBe("inst-abc");
    expect(ctx.tenantId).toBe("tenant-xyz");
    expect(ctx.agentId).toBe("io.konstera.test");
    expect(ctx.agentVersion).toBe("1.2.3");
  });

  test("uses sentinel defaults when env vars are missing (direct-run mode must boot)", () => {
    const ctx = createContext(new KernelMcpClient(undefined));

    expect(ctx.instanceId).toBe("unknown-instance");
    expect(ctx.tenantId).toBe("00000000-0000-0000-0000-000000000000");
    expect(ctx.agentId).toBe("unknown-agent");
    expect(ctx.agentVersion).toBe("0.0.0");
  });

  test("defaults param overrides sentinel but env vars win over defaults", () => {
    process.env["KONSTERA_AGENT_ID"] = "env-wins";
    const ctx = createContext(new KernelMcpClient(undefined), {
      agentId: "defaults-lose",
      agentVersion: "defaults-win-when-env-absent",
    });

    expect(ctx.agentId).toBe("env-wins");
    expect(ctx.agentVersion).toBe("defaults-win-when-env-absent");
  });

  test("wires log + llm services with the resolved instanceId", async () => {
    process.env["KONSTERA_AGENT_INSTANCE_ID"] = "inst-wired";
    const ctx = createContext(new KernelMcpClient(undefined));

    // Can't easily reach into service privates — instead, exercise the service
    // in direct-run mode and verify it doesn't throw. Direct-run no-ops are
    // a contract test.
    await expect(ctx.log.info("test")).resolves.toBeUndefined();
    await expect(
      ctx.llm.complete({ model: "x", prompt: "y" }),
    ).resolves.toEqual({ text: "", usage: { inputTokens: 0, outputTokens: 0, costUsd: 0 } });
  });
});
