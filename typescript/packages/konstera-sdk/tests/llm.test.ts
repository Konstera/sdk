/**
 * Tests for LlmService — provider-agnostic completion wrapper. Verifies result
 * parsing shape and direct-run stub behaviour.
 */
import { describe, expect, test, vi } from "vitest";
import { KernelMcpClient } from "../src/mcp.js";
import { LlmService } from "../src/services/llm.js";

describe("LlmService", () => {
  test("complete parses kernel response JSON into text + usage", async () => {
    const client = new KernelMcpClient("http://mock");
    vi.spyOn(client, "callTool").mockResolvedValue({
      disabled: false,
      content: [
        {
          type: "text",
          text: JSON.stringify({
            text: "Hello, world.",
            usage: { inputTokens: 10, outputTokens: 5, costUsd: 0.0002 },
          }),
        },
      ],
    });

    const llm = new LlmService(client, "inst-1");
    const result = await llm.complete({ model: "claude-sonnet-4-6", prompt: "Hi" });

    expect(result.text).toBe("Hello, world.");
    expect(result.usage).toEqual({ inputTokens: 10, outputTokens: 5, costUsd: 0.0002 });
  });

  test("complete passes callerInstanceId + model + prompt + options to kernel", async () => {
    const client = new KernelMcpClient("http://mock");
    const spy = vi.spyOn(client, "callTool").mockResolvedValue({
      disabled: false,
      content: [{ type: "text", text: '{"text":"ok","usage":{}}' }],
    });

    const llm = new LlmService(client, "inst-1");
    await llm.complete({
      model: "gpt-5",
      prompt: "Explain lambda calculus.",
      maxTokens: 500,
      temperature: 0.3,
    });

    expect(spy).toHaveBeenCalledWith("llm_complete", {
      callerInstanceId: "inst-1",
      model: "gpt-5",
      prompt: "Explain lambda calculus.",
      maxTokens: 500,
      temperature: 0.3,
    });
  });

  test("direct-run mode returns empty text + zero usage stub", async () => {
    const client = new KernelMcpClient(undefined);
    const llm = new LlmService(client, "inst-1");
    const result = await llm.complete({ model: "claude-sonnet-4-6", prompt: "Hi" });

    expect(result.text).toBe("");
    expect(result.usage).toEqual({ inputTokens: 0, outputTokens: 0, costUsd: 0 });
  });

  test("malformed kernel response falls back to raw text + zero usage", async () => {
    const client = new KernelMcpClient("http://mock");
    vi.spyOn(client, "callTool").mockResolvedValue({
      disabled: false,
      content: [{ type: "text", text: "not-json" }],
    });

    const llm = new LlmService(client, "inst-1");
    const result = await llm.complete({ model: "x", prompt: "y" });

    expect(result.text).toBe("not-json");
    expect(result.usage).toEqual({ inputTokens: 0, outputTokens: 0, costUsd: 0 });
  });
});
