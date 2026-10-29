"""BrowserService — drive a real browser session through the kernel.

The kernel owns the browser (where it runs is a platform concern, not
the agent's); the agent sends one step at a time by session id. Sessions are
opened against a granted connection alias, so the site credentials stay in
the tenant's connection and never reach agent code:

  - `type_secret(selector, "password")` asks the kernel to type the
    connection's secret field into the page **by reference**. The agent
    names the field; the kernel resolves and types the value. Agent code,
    logs and prompts never see it.
  - CAPTCHA, unexpected OTP prompts or any challenge the agent does not
    recognise must go to `handoff_to_human(...)`. The SDK does no CAPTCHA
    solving or detection evasion of any kind.

Session ids are kernel-issued and bound to (tenant, instance, connection);
a session from another instance is refused by the kernel.

In direct-run mode (no kernel) every call raises RuntimeError, like the
other result-returning services.
"""
from __future__ import annotations

import base64
import json
import logging
from types import TracebackType
from typing import Any

from ._mcp import KernelMcpClient

logger = logging.getLogger("konstera_sdk.browser")


def _decode(raw: Any) -> dict[str, Any]:
    """Kernel tool results are a JSON object; an empty result means `{}`."""
    if not raw:
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


class BrowserService:
    """Open kernel-hosted browser sessions against granted connections.

    The connection (e.g. an `amazon_account`) is configured once by the
    tenant in the portal and granted to this agent. The agent opens a
    session by alias and drives it with selectors. Secrets (email,
    password, TOTP) are typed by reference with `BrowserSession.type_secret`
    and never reach agent code. CAPTCHA and unknown challenges must be
    handed to a person with `BrowserSession.handoff_to_human`.

    Example:
        >>> async with await ctx.browser.open_session("amazon_uk") as page:
        ...     await page.navigate("https://www.amazon.co.uk/gp/css/order-history")
        ...     if (await page.exists("#ap_email"))["exists"]:
        ...         await page.type_secret("#ap_email", "email")
        ...         await page.click("#continue")
        ...         await page.type_secret("#ap_password", "password")
        ...         await page.click("#signInSubmit")
        ...     if (await page.exists("#captchacharacters"))["exists"]:
        ...         await page.handoff_to_human(
        ...             "Amazon is showing a CAPTCHA", until_url_contains="order-history"
        ...         )
        ...     rows = await page.extract(
        ...         ".order-card", {"id": {"selector": ".yohtmlc-order-id span"}}
        ...     )
    """

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def open_session(self, connection_alias: str) -> BrowserSession:
        """Open a browser session against a granted connection.

        Args:
            connection_alias: The alias of a connection granted to this
                agent (see `ctx.connector.list()`).

        Returns:
            A `BrowserSession`. Use it as an async context manager so the
            session is closed on exit, or call `close()` yourself.

        Raises:
            RuntimeError: No grant for the alias, no browser is available
                to the platform, or the agent runs in direct-run mode.
        """
        data = _decode(
            await self._mcp.call_tool_for_result(
                "browser_open_session",
                {"callerInstanceId": self._instance, "connectionAlias": connection_alias},
            )
        )
        return BrowserSession(
            self._mcp,
            self._instance,
            session_id=str(data.get("sessionId", "")),
            connection=data.get("connection") or {},
        )


class BrowserSession:
    """One kernel-hosted browser session. Also an async context manager;
    leaving the `async with` block closes the session.

    Secrets are typed by reference (`type_secret`) and never reach agent
    code. CAPTCHA and unknown challenges must go to `handoff_to_human`.
    """

    session_id: str
    """Kernel-issued session id, bound to (tenant, instance, connection)."""

    connection: dict[str, Any]
    """The connection the session runs under: `{"alias", "type", "config"}`.
    `config` holds only non-secret fields (e.g. the marketplace domain)."""

    def __init__(
        self,
        mcp: KernelMcpClient,
        instance_id: str,
        session_id: str,
        connection: dict[str, Any],
    ):
        self._mcp = mcp
        self._instance = instance_id
        self.session_id = session_id
        self.connection = connection
        self._closed = False

    async def __aenter__(self) -> BrowserSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc is None:
            await self.close()
            return
        # The body already failed: still try to close, but never let a close
        # failure hide the original error.
        try:
            await self.close()
        except Exception:
            logger.exception("Closing browser session %s failed", self.session_id)

    async def _call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError(f"Browser session {self.session_id} is closed.")
        payload: dict[str, Any] = {
            "callerInstanceId": self._instance,
            "sessionId": self.session_id,
        }
        payload.update({k: v for k, v in args.items() if v is not None})
        return _decode(await self._mcp.call_tool_for_result(tool, payload))

    async def navigate(self, url: str, wait_until: str = "load") -> dict[str, Any]:
        """Go to `url`. `wait_until` is `"load"`, `"domcontentloaded"` or
        `"networkidle"`. Returns `{"url", "title"}` after any redirects."""
        return await self._call("browser_navigate", {"url": url, "waitUntil": wait_until})

    async def click(self, selector: str, timeout_seconds: int = 15) -> None:
        """Click the first element matching `selector`, waiting up to
        `timeout_seconds` for it to appear."""
        await self._call(
            "browser_click", {"selector": selector, "timeoutSeconds": timeout_seconds}
        )

    async def type(self, selector: str, text: str, timeout_seconds: int = 15) -> None:
        """Type plain, non-secret `text` into `selector`. For credentials use
        `type_secret` so the value never passes through agent code."""
        await self._call(
            "browser_type",
            {"selector": selector, "text": text, "timeoutSeconds": timeout_seconds},
        )

    async def type_secret(self, selector: str, secret_field: str) -> None:
        """Type a secret of the session's connection into `selector`, by
        reference. The agent names the field (`"email"`, `"password"`, ...,
        or `"totp"` for the current code from the connection's TOTP secret);
        the kernel resolves and types the value. The secret never reaches
        agent code, logs or prompts."""
        await self._call(
            "browser_type_secret", {"selector": selector, "secretField": secret_field}
        )

    async def wait_for(
        self,
        selector: str | None = None,
        url_contains: str | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """Wait until `selector` appears and/or the URL contains
        `url_contains`. Returns `{"matched", "url"}`; `matched` is False on
        timeout."""
        return await self._call(
            "browser_wait_for",
            {
                "selector": selector,
                "urlContains": url_contains,
                "timeoutSeconds": timeout_seconds,
            },
        )

    async def exists(self, selector: str) -> dict[str, Any]:
        """Check for `selector` without waiting. Returns `{"exists", "count"}`."""
        return await self._call("browser_exists", {"selector": selector})

    async def text(self, selector: str) -> str | None:
        """Inner text of the first element matching `selector`, or None when
        nothing matches."""
        value = (await self._call("browser_text", {"selector": selector})).get("text")
        return None if value is None else str(value)

    async def extract(self, row_selector: str, fields: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract one dict per element matching `row_selector`.

        Args:
            row_selector: Selector for each row (e.g. an order card).
            fields: `{name: {"selector": str, "attr": str?, "all": bool?}}`,
                selectors relative to the row. `attr` reads an attribute
                instead of text; `all` returns a list of every match.

        Returns:
            Rows of `{name: str | list[str] | None}`.
        """
        data = await self._call(
            "browser_extract",
            {"rowSelector": row_selector, "fieldsJson": json.dumps(fields)},
        )
        rows = data.get("rows") or []
        return [r for r in rows if isinstance(r, dict)]

    async def screenshot(self, label: str) -> bytes:
        """PNG screenshot of the current page. `label` names it in the
        kernel's logs. Returns the decoded PNG bytes."""
        data = await self._call("browser_screenshot", {"label": label})
        return base64.b64decode(str(data.get("pngBase64") or ""))

    async def handoff_to_human(
        self,
        reason: str,
        until_selector: str | None = None,
        until_url_contains: str | None = None,
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        """Ask a person to act in the browser, then wait.

        Use this for every CAPTCHA, unexpected OTP prompt or challenge the
        agent does not recognise; never try to solve or evade it. The kernel
        logs a warning for the operator with `reason`, then waits until
        `until_selector` appears and/or the URL contains `until_url_contains`.

        Returns:
            `{"resolved", "url"}`; `resolved` is False on timeout.
        """
        return await self._call(
            "browser_handoff_to_human",
            {
                "reason": reason,
                "untilSelector": until_selector,
                "untilUrlContains": until_url_contains,
                "timeoutSeconds": timeout_seconds,
            },
        )

    async def close(self) -> None:
        """Close the session. Safe to call more than once."""
        if self._closed:
            return
        await self._call("browser_close_session", {})
        self._closed = True
