/**
 * Ambient invocation ID propagation via AsyncLocalStorage. Mirror of Python SDK's
 * _invocation_context.py pattern (contextvars). Lets services like LogService
 * auto-inject the invocation ID without the agent threading it manually.
 */
import { AsyncLocalStorage } from "node:async_hooks";

const storage = new AsyncLocalStorage<string>();

/** Run `fn` with the given invocation ID bound as ambient state. */
export async function enterInvocation<T>(invocationId: string, fn: () => Promise<T>): Promise<T> {
  return storage.run(invocationId, fn);
}

/** Returns the current invocation ID if we're inside enterInvocation(), else undefined. */
export function currentInvocationId(): string | undefined {
  return storage.getStore();
}
