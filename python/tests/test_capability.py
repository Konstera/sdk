"""CapabilityService (ADR-013) — purpose-first indirection over connectors.

Covers:
- `available(name)` — true/false based on kernel response, defensive parsing
- `call(name, **args)` — happy-path invocation, invocation-id injection,
  typed error unwrapping into CapabilityUnbound / CapabilityUpstreamFailed /
  CapabilityError based on the "[Code] ..." prefix the kernel surfaces
- `name` as a positional-only parameter (so capabilities with an argument
  called "name" like `db.proc.stats` still work)
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from konstera_sdk._invocation_context import enter_invocation
from konstera_sdk.capability import (
    CapabilityError,
    CapabilityService,
    CapabilityUnbound,
    CapabilityUpstreamFailed,
)


class RecordingMcp:
    def __init__(self, response: str = "", raises: Exception | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.response = response
        self.raises = raises

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        if self.raises is not None:
            raise self.raises
        return self.response


class TestAvailable:
    async def test_returns_true_when_kernel_says_available(self):
        mcp = RecordingMcp(response='{"available": true}')
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cap.available("orders.lookup_by_email") is True

    async def test_returns_false_when_kernel_says_not_available(self):
        mcp = RecordingMcp(response='{"available": false}')
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cap.available("some.capability") is False

    async def test_sends_caller_instance_id_and_name(self):
        mcp = RecordingMcp(response='{"available": true}')
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        await cap.available("tickets.reply")
        assert mcp.calls == [
            ("capability_available", {"callerInstanceId": "inst-1", "name": "tickets.reply"})
        ]

    async def test_returns_false_when_response_missing_available_key(self):
        """Defensive: unexpected shape should fail closed."""
        mcp = RecordingMcp(response='{"other": "thing"}')
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cap.available("x") is False

    async def test_returns_false_when_response_empty(self):
        mcp = RecordingMcp(response="")
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cap.available("x") is False

    async def test_returns_false_when_response_malformed_json(self):
        mcp = RecordingMcp(response="<not-json>")
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cap.available("x") is False


class TestCallHappyPath:
    async def test_returns_parsed_canonical_response(self):
        payload = {"orderId": "o-1", "status": "paid", "totalUsd": 42.5}
        mcp = RecordingMcp(response=json.dumps(payload))
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await cap.call("orders.lookup_by_id", order_id="o-1")

        assert result == payload

    async def test_sends_caller_instance_id_name_and_args_json(self):
        mcp = RecordingMcp(response="{}")
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        await cap.call("tickets.reply", ticket_id="t-1", body="hello")

        tool, args = mcp.calls[0]
        assert tool == "capability_call"
        assert args["callerInstanceId"] == "inst-1"
        assert args["name"] == "tickets.reply"
        assert json.loads(args["argsJson"]) == {"ticket_id": "t-1", "body": "hello"}

    async def test_name_is_positional_only_so_kwargs_can_contain_name(self):
        """db.proc.stats takes an argument literally called `name`. The
        positional-only slash in the signature ensures no collision."""
        mcp = RecordingMcp(response='[]')
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        await cap.call("db.proc.stats", name="dbo.procX")

        args = mcp.calls[0][1]
        # The capability name goes to the top-level "name" field
        assert args["name"] == "db.proc.stats"
        # The user's `name` kwarg lands inside argsJson
        assert json.loads(args["argsJson"]) == {"name": "dbo.procX"}

    async def test_injects_invocation_id_from_ambient_scope(self):
        mcp = RecordingMcp(response="{}")
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        async def inner():
            await cap.call("tickets.reply", ticket_id="t-1")

        with enter_invocation("inv-123"):
            await inner()

        assert mcp.calls[0][1]["invocationId"] == "inv-123"

    async def test_omits_invocation_id_outside_ambient_scope(self):
        mcp = RecordingMcp(response="{}")
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        await cap.call("tickets.reply", ticket_id="t-1")

        assert "invocationId" not in mcp.calls[0][1]

    async def test_returns_none_for_empty_response(self):
        mcp = RecordingMcp(response="")
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cap.call("some.capability") is None

    async def test_returns_raw_for_non_json_response(self):
        """Legacy or edge-case recipes might return a plain string."""
        mcp = RecordingMcp(response="plain-text-reply")
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await cap.call("some.capability") == "plain-text-reply"

    async def test_serialises_non_json_kwargs_via_default_str(self):
        import datetime as dt

        mcp = RecordingMcp(response="{}")
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        await cap.call("some.capability", as_of=dt.date(2026, 10, 21))

        args_json = mcp.calls[0][1]["argsJson"]
        assert "2026-10-21" in args_json


class TestCallTypedErrorMapping:
    """The kernel surfaces capability-layer failures as RuntimeError with
    "[Code] ..." prefixes. The SDK translates these into typed exceptions
    so agent code can `except CapabilityUnbound:` instead of parsing strings."""

    async def test_unbound_prefix_raises_capability_unbound(self):
        mcp = RecordingMcp(
            raises=RuntimeError("[Unbound] Agent has no binding for 'orders.lookup_by_id'")
        )
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        with pytest.raises(CapabilityUnbound, match=r"orders\.lookup_by_id"):
            await cap.call("orders.lookup_by_id")

    async def test_upstream_failed_prefix_raises_capability_upstream_failed(self):
        mcp = RecordingMcp(
            raises=RuntimeError("[UpstreamFailed] Shopify POST /orders failed (500)")
        )
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        with pytest.raises(CapabilityUpstreamFailed, match="Shopify"):
            await cap.call("orders.lookup_by_id")

    async def test_response_shape_invalid_prefix_raises_upstream_failed(self):
        """[ResponseShapeInvalid] means the recipe returned data that didn't
        match the canonical schema — a kind of upstream failure from the
        agent's perspective, so same exception type."""
        mcp = RecordingMcp(
            raises=RuntimeError(
                "[ResponseShapeInvalid] totalUsd missing from orders.lookup_by_id"
            )
        )
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        with pytest.raises(CapabilityUpstreamFailed, match="totalUsd"):
            await cap.call("orders.lookup_by_id")

    async def test_other_errors_raise_base_capability_error(self):
        """Fallback for errors without a known prefix — still typed
        (CapabilityError), still surfaces the kernel's message."""
        mcp = RecordingMcp(
            raises=RuntimeError("An error occurred invoking 'capability_call'.")
        )
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        with pytest.raises(CapabilityError) as exc_info:
            await cap.call("orders.lookup_by_id")

        # Must be the exact base type (not Unbound / UpstreamFailed)
        assert not isinstance(exc_info.value, CapabilityUnbound)
        assert not isinstance(exc_info.value, CapabilityUpstreamFailed)
        assert "capability_call" in str(exc_info.value)

    async def test_exception_chaining_preserves_original(self):
        """`from e` ensures the kernel error traceback is linked to the
        typed exception — critical for debugging without losing context."""
        original = RuntimeError("[Unbound] Agent has no binding")
        mcp = RecordingMcp(raises=original)
        cap = CapabilityService(mcp, "inst-1")  # type: ignore[arg-type]

        with pytest.raises(CapabilityUnbound) as exc_info:
            await cap.call("x")

        assert exc_info.value.__cause__ is original


class TestExceptionHierarchy:
    def test_all_typed_errors_subclass_capability_error(self):
        assert issubclass(CapabilityUnbound, CapabilityError)
        assert issubclass(CapabilityUpstreamFailed, CapabilityError)
        # which in turn subclasses RuntimeError so `except RuntimeError:`
        # catches everything (useful for defensive top-level handlers).
        assert issubclass(CapabilityError, RuntimeError)
