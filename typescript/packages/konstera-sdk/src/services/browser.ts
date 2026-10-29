/**
 * BrowserService — drive a real browser session through the kernel. Mirror of
 * Python's browser.py; the kernel tool names and argument names are the wire
 * contract and match it exactly.
 *
 * The kernel owns the browser (where it runs is a platform concern, not the
 * agent's); the agent sends one step at a time by session id. Sessions are
 * opened against a granted connection alias, so the site credentials stay in
 * the tenant's connection and never reach agent code:
 *
 *  - `typeSecret(selector, "password")` asks the kernel to type the
 *    connection's secret field into the page **by reference**. The agent names
 *    the field; the kernel resolves and types the value. Agent code, logs and
 *    prompts never see it.
 *  - CAPTCHA, unexpected OTP prompts or any challenge the agent does not
 *    recognise must go to `handoffToHuman(...)`. The SDK does no CAPTCHA
 *    solving or detection evasion of any kind.
 *
 * Session ids are kernel-issued and bound to (tenant, instance, connection); a
 * session from another instance is refused by the kernel.
 *
 * In direct-run mode (no kernel) every call throws, like Python.
 *
 * @example
 * ```ts
 * await using page = await ctx.browser.openSession("amazon_uk");
 * await page.navigate("https://www.amazon.co.uk/gp/css/order-history");
 * if ((await page.exists("#ap_email")).exists) {
 *   await page.typeSecret("#ap_email", "email");
 *   await page.click("#continue");
 *   await page.typeSecret("#ap_password", "password");
 *   await page.click("#signInSubmit");
 * }
 * if ((await page.exists("#captchacharacters")).exists) {
 *   await page.handoffToHuman("Amazon is showing a CAPTCHA", {
 *     untilUrlContains: "order-history",
 *   });
 * }
 * const rows = await page.extract(".order-card", {
 *   id: { selector: ".yohtmlc-order-id span" },
 * });
 * ```
 */
import type { KernelMcpClient } from "../mcp.js";

/** The connection a session runs under. `config` holds only non-secret fields. */
export interface BrowserConnection {
  readonly alias?: string;
  readonly type?: string;
  readonly config?: Record<string, unknown>;
  readonly [key: string]: unknown;
}

export type BrowserWaitUntil = "load" | "domcontentloaded" | "networkidle";

export interface NavigateResult {
  readonly url?: string;
  readonly title?: string;
  readonly [key: string]: unknown;
}

export interface WaitForResult {
  /** False on timeout. */
  readonly matched?: boolean;
  readonly url?: string;
  readonly [key: string]: unknown;
}

export interface ExistsResult {
  readonly exists?: boolean;
  readonly count?: number;
  readonly [key: string]: unknown;
}

export interface HandoffResult {
  /** False on timeout. */
  readonly resolved?: boolean;
  readonly url?: string;
  readonly [key: string]: unknown;
}

/** One extracted field: selector relative to the row; `attr` reads an attribute
 * instead of text; `all` returns every match as a list. */
export interface ExtractField {
  selector: string;
  attr?: string;
  all?: boolean;
}

export type ExtractRow = Record<string, string | string[] | null>;

export interface TimeoutOptions {
  timeoutSeconds?: number;
}

export interface WaitForOptions {
  selector?: string;
  urlContains?: string;
  /** Default 30. */
  timeoutSeconds?: number;
}

export interface HandoffOptions {
  untilSelector?: string;
  untilUrlContains?: string;
  /** Default 300. */
  timeoutSeconds?: number;
}

/** Kernel tool results are a JSON object; an empty result means `{}`. */
function decode(raw: string | null): Record<string, unknown> {
  if (!raw) return {};
  const value = JSON.parse(raw) as unknown;
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/**
 * Open kernel-hosted browser sessions against granted connections (`ctx.browser`).
 *
 * The connection (e.g. a Website login) is configured once by the tenant in
 * the portal and granted to this agent. The agent opens a session by alias and
 * drives it with selectors. Secrets are typed by reference with
 * {@link BrowserSession.typeSecret} and never reach agent code. CAPTCHA and
 * unknown challenges must be handed to a person with
 * {@link BrowserSession.handoffToHuman}.
 */
export class BrowserService {
  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;

  constructor(mcp: KernelMcpClient, instanceId: string) {
    this.mcp = mcp;
    this.instanceId = instanceId;
  }

  /**
   * Open a browser session against a granted connection.
   *
   * @param connectionAlias - The alias of a connection granted to this agent
   *   (see `ctx.connector.list()`).
   * @returns A {@link BrowserSession}. Declare it with `await using` so it is
   *   closed when the scope exits, or call `close()` yourself.
   * @throws No grant for the alias, no browser available to the platform, or
   *   direct-run mode.
   */
  async openSession(connectionAlias: string): Promise<BrowserSession> {
    const data = decode(
      await this.mcp.callToolForResult("browser_open_session", {
        callerInstanceId: this.instanceId,
        connectionAlias,
      }),
    );
    const connection = data["connection"];
    return new BrowserSession(
      this.mcp,
      this.instanceId,
      String(data["sessionId"] ?? ""),
      connection && typeof connection === "object" ? (connection as BrowserConnection) : {},
    );
  }
}

/**
 * One kernel-hosted browser session. Supports `await using` (closes on scope
 * exit). Secrets are typed by reference (`typeSecret`) and never reach agent
 * code. CAPTCHA and unknown challenges must go to `handoffToHuman`.
 */
export class BrowserSession {
  /** Kernel-issued session id, bound to (tenant, instance, connection). */
  readonly sessionId: string;

  /** The connection the session runs under: `{ alias, type, config }`.
   * `config` holds only non-secret fields (e.g. the marketplace domain). */
  readonly connection: BrowserConnection;

  private readonly mcp: KernelMcpClient;
  private readonly instanceId: string;
  private closed = false;

  constructor(
    mcp: KernelMcpClient,
    instanceId: string,
    sessionId: string,
    connection: BrowserConnection,
  ) {
    this.mcp = mcp;
    this.instanceId = instanceId;
    this.sessionId = sessionId;
    this.connection = connection;
  }

  private async call(tool: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    if (this.closed) {
      throw new Error(`Browser session ${this.sessionId} is closed.`);
    }
    const payload: Record<string, unknown> = {
      callerInstanceId: this.instanceId,
      sessionId: this.sessionId,
    };
    // Like Python, unset (undefined/null) optional arguments are not sent.
    for (const [k, v] of Object.entries(args)) {
      if (v !== undefined && v !== null) payload[k] = v;
    }
    return decode(await this.mcp.callToolForResult(tool, payload));
  }

  /** Go to `url`. Returns `{ url, title }` after any redirects. */
  async navigate(url: string, waitUntil: BrowserWaitUntil = "load"): Promise<NavigateResult> {
    return this.call("browser_navigate", { url, waitUntil });
  }

  /** Click the first element matching `selector`, waiting up to
   * `timeoutSeconds` (default 15) for it to appear. */
  async click(selector: string, options: TimeoutOptions = {}): Promise<void> {
    await this.call("browser_click", {
      selector,
      timeoutSeconds: options.timeoutSeconds ?? 15,
    });
  }

  /** Type plain, non-secret `text` into `selector`. For credentials use
   * {@link typeSecret} so the value never passes through agent code. */
  async type(selector: string, text: string, options: TimeoutOptions = {}): Promise<void> {
    await this.call("browser_type", {
      selector,
      text,
      timeoutSeconds: options.timeoutSeconds ?? 15,
    });
  }

  /**
   * Type a secret of the session's connection into `selector`, by reference.
   * The agent names the field (`"username"`, `"password"`, an extra field such
   * as `"pin"`, or `"totp"` for the current code from the connection's TOTP
   * secret); the kernel resolves and types the value. The secret never
   * reaches agent code, logs or prompts.
   */
  async typeSecret(selector: string, secretField: string): Promise<void> {
    await this.call("browser_type_secret", { selector, secretField });
  }

  /** Wait until `selector` appears and/or the URL contains `urlContains`.
   * Returns `{ matched, url }`; `matched` is false on timeout. */
  async waitFor(options: WaitForOptions = {}): Promise<WaitForResult> {
    return this.call("browser_wait_for", {
      selector: options.selector,
      urlContains: options.urlContains,
      timeoutSeconds: options.timeoutSeconds ?? 30,
    });
  }

  /** Check for `selector` without waiting. Returns `{ exists, count }`. */
  async exists(selector: string): Promise<ExistsResult> {
    return this.call("browser_exists", { selector });
  }

  /** Inner text of the first element matching `selector`, or null when
   * nothing matches. */
  async text(selector: string): Promise<string | null> {
    const value = (await this.call("browser_text", { selector }))["text"];
    return value === undefined || value === null ? null : String(value);
  }

  /**
   * Extract one row per element matching `rowSelector`.
   *
   * @param rowSelector - Selector for each row (e.g. an order card).
   * @param fields - `{ name: { selector, attr?, all? } }`, selectors relative
   *   to the row.
   * @returns Rows of `{ name: string | string[] | null }`.
   */
  async extract(
    rowSelector: string,
    fields: Record<string, ExtractField>,
  ): Promise<ExtractRow[]> {
    const data = await this.call("browser_extract", {
      rowSelector,
      fieldsJson: JSON.stringify(fields),
    });
    const rows = Array.isArray(data["rows"]) ? (data["rows"] as unknown[]) : [];
    return rows.filter(
      (r): r is ExtractRow => r !== null && typeof r === "object" && !Array.isArray(r),
    );
  }

  /** PNG screenshot of the current page. `label` names it in the kernel's
   * logs. Returns the decoded PNG bytes. */
  async screenshot(label: string): Promise<Buffer> {
    const data = await this.call("browser_screenshot", { label });
    return Buffer.from(String(data["pngBase64"] ?? ""), "base64");
  }

  /**
   * Ask a person to act in the browser, then wait.
   *
   * Use this for every CAPTCHA, unexpected OTP prompt or challenge the agent
   * does not recognise; never try to solve or evade it. The kernel logs a
   * warning for the operator with `reason`, then waits until `untilSelector`
   * appears and/or the URL contains `untilUrlContains`.
   *
   * @returns `{ resolved, url }`; `resolved` is false on timeout.
   */
  async handoffToHuman(reason: string, options: HandoffOptions = {}): Promise<HandoffResult> {
    return this.call("browser_handoff_to_human", {
      reason,
      untilSelector: options.untilSelector,
      untilUrlContains: options.untilUrlContains,
      timeoutSeconds: options.timeoutSeconds ?? 300,
    });
  }

  /** Close the session. Safe to call more than once. */
  async close(): Promise<void> {
    if (this.closed) return;
    await this.call("browser_close_session", {});
    this.closed = true;
  }

  /**
   * `await using page = await ctx.browser.openSession(...)` closes on scope
   * exit. A dispose hook can't tell whether the scope threw, and a throwing
   * dispose would wrap the scope's error in a `SuppressedError` (losing, for
   * example, an `AgentFailure` category). So a close failure here is logged,
   * never thrown. Call `close()` yourself to see close failures.
   */
  async [Symbol.asyncDispose](): Promise<void> {
    try {
      await this.close();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(`[konstera-sdk] Closing browser session ${this.sessionId} failed:`, err);
    }
  }
}
