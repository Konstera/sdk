/**
 * Tests for CredentialsService — resolve a secret by key.
 *
 * Note: tests use dummy values. In production, `ctx.credentials.get()` returns
 * real secrets — never log or echo them.
 */
import { describe, expect, test, vi } from "vitest";
import { KernelMcpClient } from "../src/mcp.js";
import { CredentialsService } from "../src/services/credentials.js";

describe("CredentialsService.get", () => {
  test("sends credentials_get with callerInstanceId + key", async () => {
    const client = new KernelMcpClient("http://mock");
    const spy = vi.spyOn(client, "callTool").mockResolvedValue({
      disabled: false,
      content: [{ type: "text", text: "sk-test-dummy-value" }],
    });

    const creds = new CredentialsService(client, "inst-1");
    const value = await creds.get("stripe-api-key");

    expect(value).toBe("sk-test-dummy-value");
    expect(spy).toHaveBeenCalledWith("credentials_get", {
      callerInstanceId: "inst-1",
      key: "stripe-api-key",
    });
  });

  test("direct-run returns empty string", async () => {
    const client = new KernelMcpClient(undefined);
    const creds = new CredentialsService(client, "inst-1");

    const value = await creds.get("stripe-api-key");

    expect(value).toBe("");
  });

  test("handles empty response gracefully", async () => {
    const client = new KernelMcpClient("http://mock");
    vi.spyOn(client, "callTool").mockResolvedValue({
      disabled: false,
      content: [],
    });

    const creds = new CredentialsService(client, "inst-1");
    expect(await creds.get("key")).toBe("");
  });
});
