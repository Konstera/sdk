/**
 * Tests for AsyncLocalStorage-based invocation ID propagation. Ensures the
 * ambient scope is properly isolated across concurrent invocations.
 */
import { describe, expect, test } from "vitest";
import { currentInvocationId, enterInvocation } from "../src/invocation-context.js";

describe("invocation-context", () => {
  test("currentInvocationId returns undefined outside enterInvocation", () => {
    expect(currentInvocationId()).toBeUndefined();
  });

  test("currentInvocationId returns the active ID inside enterInvocation", async () => {
    const captured = await enterInvocation("inv-123", async () => currentInvocationId());
    expect(captured).toBe("inv-123");
  });

  test("concurrent invocations have isolated scopes", async () => {
    const results = await Promise.all([
      enterInvocation("inv-A", async () => {
        await new Promise((r) => setTimeout(r, 10));
        return currentInvocationId();
      }),
      enterInvocation("inv-B", async () => {
        await new Promise((r) => setTimeout(r, 5));
        return currentInvocationId();
      }),
      enterInvocation("inv-C", async () => {
        return currentInvocationId();
      }),
    ]);
    expect(results).toEqual(["inv-A", "inv-B", "inv-C"]);
  });

  test("scope cleared after enterInvocation resolves", async () => {
    await enterInvocation("inv-nested", async () => {
      expect(currentInvocationId()).toBe("inv-nested");
    });
    expect(currentInvocationId()).toBeUndefined();
  });
});
