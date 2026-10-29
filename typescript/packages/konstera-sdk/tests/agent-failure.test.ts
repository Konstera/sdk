/**
 * AgentFailure carries a category the runtime puts in the /invoke error body.
 * Mirror of Python's tests/test_agent_failure.py; the error body must match
 * what the Python runtime sends: {"type", "message", "category"?}.
 */
import type { AddressInfo } from "node:net";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Agent } from "../src/agent.js";
import { createContext } from "../src/context.js";
import type { AgentContext } from "../src/context.js";
import * as sdk from "../src/index.js";
import { KernelMcpClient } from "../src/mcp.js";
import { buildServer, invokeErrorBody } from "../src/runtime.js";
import { AgentFailure } from "../src/types.js";
import type { AgentRequest, AgentResponse } from "../src/types.js";

class Refused extends AgentFailure {
  static override readonly defaultCategory = AgentFailure.ACTION_NEEDED;
}

class FailingAgent extends Agent {
  constructor(private readonly err: unknown) {
    super();
  }
  override async handle(_req: AgentRequest, _ctx: AgentContext): Promise<AgentResponse> {
    throw this.err;
  }
}

afterEach(() => vi.restoreAllMocks());

/** POST /invoke against a real server on an ephemeral port; return status + error body. */
async function invoke(err: unknown): Promise<Record<string, unknown>> {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const ctx = createContext(new KernelMcpClient(undefined));
  const server = buildServer(new FailingAgent(err), ctx);
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  try {
    const { port } = server.address() as AddressInfo;
    const res = await fetch(`http://127.0.0.1:${port}/invoke`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ invocationId: "i1", input: "" }),
    });
    expect(res.status).toBe(500);
    const body = (await res.json()) as { error: Record<string, unknown> };
    return body.error;
  } finally {
    await new Promise<void>((r) => server.close(() => r()));
  }
}

describe("runtime reports the failure category", () => {
  test("declared category is sent (same body as Python)", async () => {
    const err = await invoke(new AgentFailure("site down", { category: "dependency_failure" }));
    expect(err).toEqual({ type: "AgentFailure", message: "site down", category: "dependency_failure" });
  });

  test("each declarable category passes through unchanged", async () => {
    for (const category of [
      "dependency_failure",
      "action_needed",
      "input_invalid",
      "credential_missing",
    ] as const) {
      expect((await invoke(new AgentFailure("x", { category })))["category"]).toBe(category);
    }
  });

  test("subclass default category is sent, with the subclass name as type", async () => {
    const err = await invoke(new Refused("fix the connection"));
    expect(err).toEqual({ type: "Refused", message: "fix the connection", category: "action_needed" });
  });

  test("explicit category beats the subclass default", async () => {
    const err = await invoke(new Refused("x", { category: "input_invalid" }));
    expect(err["category"]).toBe("input_invalid");
  });

  test("plain error has no category", async () => {
    const err = await invoke(new Error("boom"));
    expect(err).toEqual({ type: "Error", message: "boom" });
    expect(err).not.toHaveProperty("category");
  });

  test("any error with a string category attribute is reported (duck-typed, like Python)", async () => {
    const e = Object.assign(new Error("401 from upstream"), { category: "credential_missing" });
    expect((await invoke(e))["category"]).toBe("credential_missing");
  });
});

describe("invokeErrorBody", () => {
  test("ignores empty and non-string categories", () => {
    expect(invokeErrorBody(Object.assign(new Error("a"), { category: "" })).error).not.toHaveProperty("category");
    expect(invokeErrorBody(Object.assign(new Error("a"), { category: 3 })).error).not.toHaveProperty("category");
  });
  test("non-Error throwables", () => {
    expect(invokeErrorBody("nope")).toEqual({ error: { type: "Error", message: "nope" } });
    expect(invokeErrorBody(null)).toEqual({ error: { type: "Error", message: "null" } });
  });
});

describe("AgentFailure", () => {
  test("default category is dependency_failure", () => {
    expect(new AgentFailure("x").category).toBe("dependency_failure");
  });
  test("is an Error with name AgentFailure and keeps cause", () => {
    const cause = new Error("root");
    const f = new AgentFailure("x", { cause });
    expect(f).toBeInstanceOf(Error);
    expect(f.name).toBe("AgentFailure");
    expect(f.message).toBe("x");
    expect(f.cause).toBe(cause);
  });
  test("constants match the Python names", () => {
    expect([
      AgentFailure.DEPENDENCY_FAILURE,
      AgentFailure.ACTION_NEEDED,
      AgentFailure.INPUT_INVALID,
      AgentFailure.CREDENTIAL_MISSING,
    ]).toEqual(["dependency_failure", "action_needed", "input_invalid", "credential_missing"]);
  });
  test("exported from the package entry", () => {
    expect(sdk.AgentFailure).toBe(AgentFailure);
  });
});
