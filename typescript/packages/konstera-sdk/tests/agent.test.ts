/**
 * Tests for the Agent base class — default lifecycle methods and the required
 * handle() override contract.
 */
import { describe, expect, test, vi } from "vitest";
import { Agent } from "../src/agent.js";
import { createContext } from "../src/context.js";
import { KernelMcpClient } from "../src/mcp.js";
import type { AgentRequest, AgentResponse } from "../src/types.js";

const emptyCtx = createContext(new KernelMcpClient(undefined));
const emptyReq: AgentRequest = {
  invocationId: "test",
  input: "",
  payload: null,
  config: {},
};

describe("Agent", () => {
  test("default initialize is a no-op", async () => {
    const agent = new (class extends Agent {
      async handle(_r: AgentRequest, _c: typeof emptyCtx): Promise<AgentResponse> {
        return { content: "" };
      }
    })();
    await expect(agent.initialize(emptyCtx)).resolves.toBeUndefined();
  });

  test("default shutdown is a no-op", async () => {
    const agent = new (class extends Agent {
      async handle(_r: AgentRequest, _c: typeof emptyCtx): Promise<AgentResponse> {
        return { content: "" };
      }
    })();
    await expect(agent.shutdown(emptyCtx)).resolves.toBeUndefined();
  });

  test("default handle throws instructing the author to override", async () => {
    const agent = new (class extends Agent {})();
    await expect(agent.handle(emptyReq, emptyCtx)).rejects.toThrow(/override/);
  });

  test("overriding handle works and receives both req and ctx", async () => {
    const spy = vi.fn(async (): Promise<AgentResponse> => ({ content: "ok" }));
    const agent = new (class extends Agent {
      async handle(req: AgentRequest, ctx: typeof emptyCtx): Promise<AgentResponse> {
        return spy(req, ctx);
      }
    })();

    const result = await agent.handle(emptyReq, emptyCtx);
    expect(result).toEqual({ content: "ok" });
    expect(spy).toHaveBeenCalledWith(emptyReq, emptyCtx);
  });
});
