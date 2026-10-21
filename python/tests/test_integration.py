"""Integration tests — exercise the full /health, /describe, /invoke surface
end-to-end through a Starlette TestClient, with a recording MCP mock so we
can verify both the HTTP response AND the kernel-side side effects the
agent produced.

These are the "end-to-end" tests that cover `runtime.build_app()` + agent
lifecycle + invocation-id propagation + response serialisation + error
handling in one roundtrip per test. Previously the runtime module was
untested (42% coverage); this file covers the HTTP layer end-to-end.
"""
from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from konstera_sdk import Agent, AgentContext, AgentRequest, AgentResponse
from konstera_sdk._invocation_context import current_invocation_id
from konstera_sdk._mcp import KernelMcpClient
from konstera_sdk.runtime import build_app


class RecordingMcp(KernelMcpClient):
    """A KernelMcpClient subclass that records calls instead of hitting a kernel.

    Returns a canned response per tool. Used by every integration test to
    assert what the agent sent to the kernel without needing a live
    endpoint.
    """

    def __init__(self, responses: dict[str, str] | None = None):
        # Pass a URL so .enabled is True (services won't short-circuit to
        # "requires-kernel" errors) — but we never actually connect.
        super().__init__("http://mock-kernel")
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses = responses or {}

    async def call_tool(self, tool: str, args: dict[str, Any]) -> None:
        """Mirrors KernelMcpClient.call_tool — records + returns None."""
        self.calls.append((tool, args))

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        """Mirrors KernelMcpClient.call_tool_for_result — records + returns canned."""
        self.calls.append((tool, args))
        return self.responses.get(tool, "")


class EchoAgent(Agent):
    """Minimal agent — returns `Hello, <input>` and logs an info line."""

    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        name = req.input.strip() or "world"
        await ctx.log.info(f"Hello, {name}!", echo_of=name)
        return AgentResponse(content=f"Hello, {name}!")


class StructuredAgent(Agent):
    """Returns a structured payload alongside the text content."""

    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        return AgentResponse(
            content="processed",
            structured={"items": 3, "input_echo": req.input},
        )


class InvocationIdCapturingAgent(Agent):
    """Captures `current_invocation_id()` to prove the ambient scope is active
    inside `handle()`."""

    def __init__(self) -> None:
        self.captured_invocation_id: str | None = None

    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        self.captured_invocation_id = current_invocation_id()
        return AgentResponse(content="")


class RaisingAgent(Agent):
    """Deliberately throws, so we can verify the error-handling path."""

    class SentinelError(Exception):
        pass

    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        raise RaisingAgent.SentinelError("intentional failure for testing")


class LifecycleTrackingAgent(Agent):
    """Records which lifecycle methods were called in which order."""

    def __init__(self) -> None:
        self.events: list[str] = []

    async def initialize(self, ctx: AgentContext) -> None:
        self.events.append("initialize")

    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        self.events.append("handle")
        return AgentResponse(content="")

    async def shutdown(self, ctx: AgentContext) -> None:
        self.events.append("shutdown")


def _make_ctx(mcp: RecordingMcp | None = None, **defaults: str) -> AgentContext:
    """Builds an AgentContext with sensible defaults and the given mock MCP."""
    return AgentContext.from_env(
        mcp or RecordingMcp(),
        defaults={
            "instance_id": "test-instance-id",
            "tenant_id": "test-tenant-id",
            "agent_id": "io.konstera.test",
            "agent_version": "0.0.1",
            **defaults,
        },
    )


class TestHealthEndpoint:
    def test_returns_agent_identity(self):
        ctx = _make_ctx()
        app = build_app(EchoAgent(), ctx)
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "agent": "io.konstera.test",
            "version": "0.0.1",
        }

    def test_health_does_not_require_kernel(self):
        """Health check works in direct-run mode too — important for
        container healthchecks before the kernel wires up."""
        ctx = AgentContext.from_env(KernelMcpClient(None))
        app = build_app(EchoAgent(), ctx)
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestDescribeEndpoint:
    def test_returns_agent_metadata(self):
        ctx = _make_ctx()
        app = build_app(EchoAgent(), ctx)
        with TestClient(app) as client:
            resp = client.get("/describe")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "io.konstera.test"
        assert body["version"] == "0.0.1"
        assert "kernel-mcp-callback" in body["capabilities"]


class TestInvokeEndpoint:
    def test_happy_path_echoes_input(self):
        ctx = _make_ctx()
        app = build_app(EchoAgent(), ctx)
        with TestClient(app) as client:
            resp = client.post("/invoke", json={"invocationId": "inv-1", "input": "Alice"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "Hello, Alice!"
        assert body["structured"] is None
        assert body["toolCalls"] == []

    def test_empty_input_defaults_to_world(self):
        ctx = _make_ctx()
        app = build_app(EchoAgent(), ctx)
        with TestClient(app) as client:
            resp = client.post("/invoke", json={"invocationId": "inv-2", "input": ""})
        assert resp.status_code == 200
        assert resp.json()["content"] == "Hello, world!"

    def test_missing_invocation_id_defaults_to_sentinel(self):
        """The kernel always sends invocationId, but a bare curl might not —
        the SDK should still accept and label the invocation 'missing' so
        logs are still correlated to a well-known string."""
        ctx = _make_ctx()
        app = build_app(EchoAgent(), ctx)
        with TestClient(app) as client:
            resp = client.post("/invoke", json={"input": "Bob"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "Hello, Bob!"

    def test_structured_response_is_serialised(self):
        ctx = _make_ctx()
        app = build_app(StructuredAgent(), ctx)
        with TestClient(app) as client:
            resp = client.post(
                "/invoke", json={"invocationId": "inv-3", "input": "sample"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "processed"
        assert body["structured"] == {"items": 3, "input_echo": "sample"}

    def test_payload_and_config_are_passed_through(self):
        """Verify payload + config survive the HTTP serialisation roundtrip."""
        received: dict[str, Any] = {}

        class ConfigReadingAgent(Agent):
            async def handle(
                self, req: AgentRequest, ctx: AgentContext
            ) -> AgentResponse:
                received["payload"] = req.payload
                received["config"] = req.config
                return AgentResponse(content="")

        ctx = _make_ctx()
        app = build_app(ConfigReadingAgent(), ctx)
        with TestClient(app) as client:
            resp = client.post(
                "/invoke",
                json={
                    "invocationId": "inv-4",
                    "input": "x",
                    "payload": {"key": "value", "nested": {"a": 1}},
                    "config": {"max_retries": 3, "mode": "strict"},
                },
            )
        assert resp.status_code == 200
        assert received["payload"] == {"key": "value", "nested": {"a": 1}}
        assert received["config"] == {"max_retries": 3, "mode": "strict"}

    def test_handler_exception_returns_500_with_structured_error(self):
        ctx = _make_ctx()
        app = build_app(RaisingAgent(), ctx)
        with TestClient(app) as client:
            resp = client.post(
                "/invoke", json={"invocationId": "inv-err", "input": "x"},
            )
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["type"] == "SentinelError"
        assert "intentional failure" in body["error"]["message"]


class TestInvocationIdPropagation:
    def test_invocation_id_available_in_handle_via_ambient_scope(self):
        agent = InvocationIdCapturingAgent()
        ctx = _make_ctx()
        app = build_app(agent, ctx)
        with TestClient(app) as client:
            client.post("/invoke", json={"invocationId": "inv-captured", "input": ""})
        assert agent.captured_invocation_id == "inv-captured"

    def test_concurrent_invocations_have_isolated_ids(self):
        """Multiple requests should see their own invocation IDs — no bleed
        from the AsyncLocalStorage-style scope mechanism."""
        captured: dict[str, str | None] = {}

        class RecordingAgent(Agent):
            async def handle(
                self, req: AgentRequest, ctx: AgentContext
            ) -> AgentResponse:
                captured[req.invocation_id] = current_invocation_id()
                return AgentResponse(content="")

        ctx = _make_ctx()
        app = build_app(RecordingAgent(), ctx)
        with TestClient(app) as client:
            client.post("/invoke", json={"invocationId": "inv-A", "input": ""})
            client.post("/invoke", json={"invocationId": "inv-B", "input": ""})
            client.post("/invoke", json={"invocationId": "inv-C", "input": ""})

        assert captured == {"inv-A": "inv-A", "inv-B": "inv-B", "inv-C": "inv-C"}

    def test_invocation_scope_cleared_after_handle_returns(self):
        """The ambient scope must not leak outside handle() — fire a request,
        wait, and verify the scope is empty."""
        ctx = _make_ctx()
        app = build_app(EchoAgent(), ctx)
        with TestClient(app) as client:
            client.post("/invoke", json={"invocationId": "inv-leak-test", "input": ""})
        # Outside the TestClient context, no invocation should be active
        assert current_invocation_id() is None


class TestKernelCallIntegration:
    """Verifies kernel-side side effects (log calls, tool calls) are actually
    sent to the mock MCP during an invocation — closes the loop between the
    HTTP transport, the invocation-scope wiring, and the service layer."""

    def test_log_call_sent_to_kernel_with_invocation_id(self):
        mcp = RecordingMcp()
        ctx = _make_ctx(mcp=mcp)
        app = build_app(EchoAgent(), ctx)
        with TestClient(app) as client:
            client.post(
                "/invoke", json={"invocationId": "inv-log", "input": "Carol"},
            )
        assert len(mcp.calls) == 1
        tool, args = mcp.calls[0]
        assert tool == "log_info"
        assert args["callerInstanceId"] == "test-instance-id"
        assert args["invocationId"] == "inv-log"
        assert "Hello, Carol!" in args["message"]


class TestLifecycle:
    def test_initialize_fires_before_handle(self):
        agent = LifecycleTrackingAgent()
        ctx = _make_ctx()
        app = build_app(agent, ctx)
        with TestClient(app) as client:
            client.post("/invoke", json={"invocationId": "inv-lc", "input": ""})
        # Starlette's TestClient enters the lifespan on __enter__ and leaves on __exit__
        assert agent.events == ["initialize", "handle", "shutdown"]

    def test_shutdown_fires_even_if_handle_raised(self):
        """Lifecycle shutdown must still fire on graceful stop even if
        handle() raised — otherwise connections leak."""
        events: list[str] = []

        class BrittleAgent(Agent):
            async def initialize(self, ctx: AgentContext) -> None:
                events.append("initialize")

            async def handle(
                self, req: AgentRequest, ctx: AgentContext
            ) -> AgentResponse:
                events.append("handle-raised")
                raise RuntimeError("fail")

            async def shutdown(self, ctx: AgentContext) -> None:
                events.append("shutdown")

        ctx = _make_ctx()
        app = build_app(BrittleAgent(), ctx)
        with TestClient(app) as client:
            resp = client.post(
                "/invoke", json={"invocationId": "inv-brittle", "input": ""},
            )
        assert resp.status_code == 500
        assert events == ["initialize", "handle-raised", "shutdown"]
