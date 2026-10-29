/**
 * BrowserService — kernel-hosted browser sessions. Mirror of Python's
 * tests/test_browser.py: tool name + argument mapping per method (the wire
 * contract), JSON decoding, screenshot base64 decoding, close/dispose,
 * error propagation and direct-run mode. Plus secrets-by-reference checks.
 */
import { describe, expect, test, vi } from "vitest";
import * as sdk from "../src/index.js";
import { createContext } from "../src/context.js";
import { KernelMcpClient, toolResultText } from "../src/mcp.js";
import { BrowserService, BrowserSession } from "../src/services/browser.js";

const OPEN_RESPONSE = JSON.stringify({
  sessionId: "sess-1",
  connection: { alias: "amazon_uk", type: "amazon_account", config: { domain: "amazon.co.uk" } },
});

const BASE = { callerInstanceId: "inst-1", sessionId: "sess-1" };

type Call = { name: string; args: Record<string, unknown> };

/** Fake kernel. `responses` maps tool -> raw result text; `errors` maps tool -> error. */
function recordingMcp(
  responses: Record<string, string | null> = {},
  errors: Record<string, Error> = {},
) {
  const calls: Call[] = [];
  const all: Record<string, string | null> = { browser_open_session: OPEN_RESPONSE, ...responses };
  const client = new KernelMcpClient("http://mock");
  const callTool = vi.spyOn(client, "callTool");
  vi.spyOn(client, "callToolForResult").mockImplementation(async (name, args) => {
    calls.push({ name, args });
    const err = errors[name];
    if (err) throw err;
    return name in all ? all[name]! : "{}";
  });
  const last = (): Call => calls[calls.length - 1]!;
  return { client, calls, last, callTool };
}

async function openSession(mcp: KernelMcpClient): Promise<BrowserSession> {
  return new BrowserService(mcp, "inst-1").openSession("amazon_uk");
}

describe("openSession", () => {
  test("sends alias and instance", async () => {
    const m = recordingMcp();
    await openSession(m.client);
    expect(m.calls).toEqual([
      {
        name: "browser_open_session",
        args: { callerInstanceId: "inst-1", connectionAlias: "amazon_uk" },
      },
    ]);
  });

  test("decodes session and connection", async () => {
    const s = await openSession(recordingMcp().client);
    expect(s).toBeInstanceOf(BrowserSession);
    expect(s.sessionId).toBe("sess-1");
    expect(s.connection).toEqual({
      alias: "amazon_uk",
      type: "amazon_account",
      config: { domain: "amazon.co.uk" },
    });
  });

  test("tolerates empty response", async () => {
    const s = await openSession(recordingMcp({ browser_open_session: "" }).client);
    expect(s.sessionId).toBe("");
    expect(s.connection).toEqual({});
  });

  test("error propagates", async () => {
    const m = recordingMcp({}, { browser_open_session: new Error("[NotGranted] no") });
    await expect(openSession(m.client)).rejects.toThrow(/NotGranted/);
  });
});

describe("tool mapping (wire contract)", () => {
  test("navigate", async () => {
    const m = recordingMcp({ browser_navigate: '{"url": "https://x/y", "title": "Y"}' });
    const s = await openSession(m.client);
    expect(await s.navigate("https://x")).toEqual({ url: "https://x/y", title: "Y" });
    expect(m.last()).toEqual({
      name: "browser_navigate",
      args: { ...BASE, url: "https://x", waitUntil: "load" },
    });
    await s.navigate("https://x", "networkidle");
    expect(m.last().args["waitUntil"]).toBe("networkidle");
  });

  test("click", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    expect(await s.click("#go")).toBeUndefined();
    expect(m.last()).toEqual({
      name: "browser_click",
      args: { ...BASE, selector: "#go", timeoutSeconds: 15 },
    });
    await s.click("#go", { timeoutSeconds: 3 });
    expect(m.last().args["timeoutSeconds"]).toBe(3);
  });

  test("type", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    expect(await s.type("#q", "hello")).toBeUndefined();
    expect(m.last()).toEqual({
      name: "browser_type",
      args: { ...BASE, selector: "#q", text: "hello", timeoutSeconds: 15 },
    });
    await s.type("#q", "hello", { timeoutSeconds: 4 });
    expect(m.last().args["timeoutSeconds"]).toBe(4);
  });

  test("typeSecret", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    expect(await s.typeSecret("#ap_password", "password")).toBeUndefined();
    expect(m.last()).toEqual({
      name: "browser_type_secret",
      args: { ...BASE, selector: "#ap_password", secretField: "password" },
    });
  });

  test("waitFor omits unset conditions", async () => {
    const m = recordingMcp({ browser_wait_for: '{"matched": true, "url": "https://x"}' });
    const s = await openSession(m.client);
    expect(await s.waitFor({ selector: "#orders" })).toEqual({ matched: true, url: "https://x" });
    expect(m.last()).toEqual({
      name: "browser_wait_for",
      args: { ...BASE, selector: "#orders", timeoutSeconds: 30 },
    });
    await s.waitFor({ urlContains: "order-history", timeoutSeconds: 5 });
    expect(m.last().args).toEqual({ ...BASE, urlContains: "order-history", timeoutSeconds: 5 });
  });

  test("exists", async () => {
    const m = recordingMcp({ browser_exists: '{"exists": true, "count": 3}' });
    const s = await openSession(m.client);
    expect(await s.exists(".card")).toEqual({ exists: true, count: 3 });
    expect(m.last()).toEqual({ name: "browser_exists", args: { ...BASE, selector: ".card" } });
  });

  test("text", async () => {
    const m = recordingMcp({ browser_text: '{"text": "Order #1"}' });
    const s = await openSession(m.client);
    expect(await s.text("h1")).toBe("Order #1");
    expect(m.last()).toEqual({ name: "browser_text", args: { ...BASE, selector: "h1" } });
  });

  test("text is null when nothing matches", async () => {
    const s = await openSession(recordingMcp({ browser_text: '{"text": null}' }).client);
    expect(await s.text("h1")).toBeNull();
  });

  test("extract serialises fieldsJson", async () => {
    const rows = [
      { id: "1", items: ["a", "b"] },
      { id: "2", items: [] },
    ];
    const m = recordingMcp({ browser_extract: JSON.stringify({ rows }) });
    const s = await openSession(m.client);
    const fields = { id: { selector: ".id" }, items: { selector: ".item", all: true } };
    expect(await s.extract(".order", fields)).toEqual(rows);
    const { name, args } = m.last();
    expect(name).toBe("browser_extract");
    expect(args["rowSelector"]).toBe(".order");
    expect(JSON.parse(args["fieldsJson"] as string)).toEqual(fields);
    expect(Object.keys(args).sort()).toEqual(
      ["callerInstanceId", "fieldsJson", "rowSelector", "sessionId"],
    );
  });

  test("extract with null rows returns []", async () => {
    const s = await openSession(recordingMcp({ browser_extract: '{"rows": null}' }).client);
    expect(await s.extract(".order", {})).toEqual([]);
  });

  test("screenshot decodes base64", async () => {
    const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x66]);
    const m = recordingMcp({
      browser_screenshot: JSON.stringify({ pngBase64: png.toString("base64") }),
    });
    const s = await openSession(m.client);
    expect(Buffer.compare(await s.screenshot("after-login"), png)).toBe(0);
    expect(m.last()).toEqual({
      name: "browser_screenshot",
      args: { ...BASE, label: "after-login" },
    });
  });

  test("screenshot empty", async () => {
    const s = await openSession(recordingMcp({ browser_screenshot: "{}" }).client);
    expect((await s.screenshot("x")).length).toBe(0);
  });

  test("handoffToHuman", async () => {
    const m = recordingMcp({ browser_handoff_to_human: '{"resolved": true, "url": "https://o"}' });
    const s = await openSession(m.client);
    const result = await s.handoffToHuman("CAPTCHA shown", { untilUrlContains: "order-history" });
    expect(result).toEqual({ resolved: true, url: "https://o" });
    expect(m.last()).toEqual({
      name: "browser_handoff_to_human",
      args: {
        ...BASE,
        reason: "CAPTCHA shown",
        untilUrlContains: "order-history",
        timeoutSeconds: 300,
      },
    });
    await s.handoffToHuman("OTP", { untilSelector: "#orders", timeoutSeconds: 60 });
    expect(m.last().args).toEqual({
      ...BASE,
      reason: "OTP",
      untilSelector: "#orders",
      timeoutSeconds: 60,
    });
  });

  test("non-object response decodes to {}", async () => {
    const s = await openSession(recordingMcp({ browser_exists: "[1, 2]" }).client);
    expect(await s.exists("x")).toEqual({});
  });

  test("close", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    expect(await s.close()).toBeUndefined();
    expect(m.last()).toEqual({ name: "browser_close_session", args: BASE });
  });

  test("tool names match the Python SDK byte for byte", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    await s.navigate("u");
    await s.click("a");
    await s.type("a", "t");
    await s.typeSecret("a", "password");
    await s.waitFor({ selector: "a" });
    await s.exists("a");
    await s.text("a");
    await s.extract("a", {});
    await s.screenshot("l");
    await s.handoffToHuman("r");
    await s.close();
    expect(m.calls.map((c) => c.name)).toEqual([
      "browser_open_session",
      "browser_navigate",
      "browser_click",
      "browser_type",
      "browser_type_secret",
      "browser_wait_for",
      "browser_exists",
      "browser_text",
      "browser_extract",
      "browser_screenshot",
      "browser_handoff_to_human",
      "browser_close_session",
    ]);
  });
});

describe("secrets by reference", () => {
  test("typeSecret sends only the field name: no value key, no credential lookup", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    await s.typeSecret("#ap_email", "username");
    await s.typeSecret("#otp", "totp");
    const secretCalls = m.calls.filter((c) => c.name === "browser_type_secret");
    expect(secretCalls).toHaveLength(2);
    for (const c of secretCalls) {
      expect(Object.keys(c.args).sort()).toEqual(
        ["callerInstanceId", "secretField", "selector", "sessionId"],
      );
      expect(c.args).not.toHaveProperty("text");
      expect(c.args).not.toHaveProperty("value");
    }
    expect(secretCalls.map((c) => c.args["secretField"])).toEqual(["username", "totp"]);
    // The SDK never resolves the secret itself: no credentials_get, nothing via callTool.
    expect(m.calls.some((c) => c.name === "credentials_get")).toBe(false);
    expect(m.callTool).not.toHaveBeenCalled();
  });

  test("a value can't be passed, and nothing extra reaches the wire", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    // @ts-expect-error — typeSecret takes the field name only, never a value.
    await s.typeSecret("#ap_password", "password", "hunter2");
    expect(JSON.stringify(m.calls)).not.toContain("hunter2");
    expect(m.last().args).toEqual({ ...BASE, selector: "#ap_password", secretField: "password" });
  });
});

describe("lifecycle", () => {
  test("Symbol.asyncDispose closes", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    await s.click("#a");
    await s[Symbol.asyncDispose]();
    expect(m.calls.map((c) => c.name)).toEqual([
      "browser_open_session",
      "browser_click",
      "browser_close_session",
    ]);
  });

  test("dispose after a body error closes and keeps the original error", async () => {
    const m = recordingMcp({}, { browser_close_session: new Error("close failed") });
    const s = await openSession(m.client);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const body = async (): Promise<void> => {
      try {
        throw new Error("boom");
      } finally {
        await s[Symbol.asyncDispose]();
      }
    };
    await expect(body()).rejects.toThrow("boom");
    expect(m.last().name).toBe("browser_close_session");
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });

  test("explicit close() propagates a close error", async () => {
    const m = recordingMcp({}, { browser_close_session: new Error("close failed") });
    const s = await openSession(m.client);
    await expect(s.close()).rejects.toThrow("close failed");
  });

  test("close is idempotent", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    await s.close();
    await s.close();
    await s[Symbol.asyncDispose]();
    expect(m.calls.filter((c) => c.name === "browser_close_session")).toHaveLength(1);
  });

  test("calls after close throw", async () => {
    const m = recordingMcp();
    const s = await openSession(m.client);
    await s.close();
    await expect(s.click("#a")).rejects.toThrow(/closed/);
  });

  test("tool error propagates", async () => {
    const m = recordingMcp({}, { browser_click: new Error("[Timeout] #a not found") });
    const s = await openSession(m.client);
    await expect(s.click("#a")).rejects.toThrow(/Timeout/);
  });
});

describe("toolResultText (callToolForResult decoding)", () => {
  test("joins text blocks", () => {
    expect(toolResultText("t", { content: [{ type: "text", text: "a" }, { type: "text", text: "b" }] })).toBe("ab");
  });
  test("null when no text", () => {
    expect(toolResultText("t", { content: [] })).toBeNull();
  });
  test("isError throws with the kernel message", () => {
    expect(() =>
      toolResultText("t", { isError: true, content: [{ type: "text", text: "[NotGranted] no" }] }),
    ).toThrow("[NotGranted] no");
  });
  test("isError without text throws a generic message", () => {
    expect(() => toolResultText("browser_click", { isError: true, content: [] })).toThrow(
      /browser_click' failed/,
    );
  });
});

describe("wiring", () => {
  test("exported from the package entry", () => {
    expect(sdk.BrowserService).toBe(BrowserService);
    expect(sdk.BrowserSession).toBe(BrowserSession);
  });

  test("context exposes browser", () => {
    const ctx = createContext(new KernelMcpClient(undefined));
    expect(ctx.browser).toBeInstanceOf(BrowserService);
  });

  test("direct-run mode throws a clear error", async () => {
    const ctx = createContext(new KernelMcpClient(undefined));
    await expect(ctx.browser.openSession("amazon_uk")).rejects.toThrow(
      /KONSTERA_KERNEL_MCP_URL is unset/,
    );
  });
});
