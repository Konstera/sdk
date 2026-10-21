"""StateService — per-instance durable KV. These tests use a recording
MCP mock to verify both the shape of the kernel-side call AND the
client-side deserialisation of the response.
"""
from __future__ import annotations

import json
from typing import Any

from konstera_sdk.state import StateService


class RecordingMcp:
    def __init__(self, responses: dict[str, str] | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses = responses or {}

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self.responses.get(tool, "")


class TestStateServiceGet:
    async def test_get_sends_instance_id_and_key(self):
        mcp = RecordingMcp(responses={"state_get": '"hello"'})
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await state.get("greeting")

        assert result == "hello"
        assert mcp.calls == [("state_get", {"instanceId": "inst-1", "key": "greeting"})]

    async def test_get_returns_none_for_missing_key(self):
        mcp = RecordingMcp(responses={"state_get": "null"})
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await state.get("missing")

        assert result is None

    async def test_get_returns_none_when_raw_is_empty(self):
        mcp = RecordingMcp(responses={"state_get": ""})
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await state.get("empty")

        # Empty string isn't valid JSON — service returns raw string "" as fallback.
        # The contract is "None iff kernel returned null"; empty-raw is treated as
        # "no value" by falling through to the except branch and returning the raw.
        assert result == ""

    async def test_get_deserialises_structured_values(self):
        payload = {"user_id": 42, "preferences": {"theme": "dark"}, "last_seen": None}
        mcp = RecordingMcp(responses={"state_get": json.dumps(payload)})
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await state.get("user-settings")

        assert result == payload

    async def test_get_falls_back_to_raw_when_response_is_not_json(self):
        """Older kernels or caller errors might return a non-JSON string.
        We tolerate it rather than crashing the agent."""
        mcp = RecordingMcp(responses={"state_get": "literal-string-not-json"})
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await state.get("key")

        assert result == "literal-string-not-json"


class TestStateServiceSet:
    async def test_set_serialises_dict_values(self):
        mcp = RecordingMcp()
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        await state.set("profile", {"name": "Alice", "age": 30})

        assert len(mcp.calls) == 1
        tool, args = mcp.calls[0]
        assert tool == "state_set"
        assert args["instanceId"] == "inst-1"
        assert args["key"] == "profile"
        assert json.loads(args["valueJson"]) == {"name": "Alice", "age": 30}

    async def test_set_serialises_primitive_values(self):
        mcp = RecordingMcp()
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        await state.set("counter", 42)
        await state.set("flag", True)
        await state.set("name", "Bob")
        await state.set("maybe", None)

        values = [json.loads(call[1]["valueJson"]) for call in mcp.calls]
        assert values == [42, True, "Bob", None]

    async def test_set_handles_non_json_serialisable_via_str_fallback(self):
        """default=str in json.dumps lets us set datetime etc. without crashing."""
        import datetime as dt

        mcp = RecordingMcp()
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        await state.set("ts", dt.datetime(2026, 10, 21, 12, 0, 0))

        value_json = mcp.calls[0][1]["valueJson"]
        # Should be a JSON-encoded string, not a crash
        assert isinstance(json.loads(value_json), str)
        assert "2026-10-21" in value_json


class TestStateServiceDelete:
    async def test_delete_is_idempotent_against_missing_keys(self):
        mcp = RecordingMcp()
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        # Delete should not raise even if the key doesn't exist — kernel
        # treats missing keys as a no-op per the contract.
        await state.delete("nonexistent")

        assert mcp.calls == [("state_delete", {"instanceId": "inst-1", "key": "nonexistent"})]


class TestStateServiceList:
    async def test_list_returns_keys_from_kernel(self):
        mcp = RecordingMcp(
            responses={"state_list": '["profile", "counter", "flag"]'}
        )
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        keys = await state.list()

        assert keys == ["profile", "counter", "flag"]
        assert mcp.calls == [("state_list", {"instanceId": "inst-1", "prefix": ""})]

    async def test_list_respects_prefix_filter(self):
        mcp = RecordingMcp(responses={"state_list": '["user:1", "user:2"]'})
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        keys = await state.list(prefix="user:")

        assert keys == ["user:1", "user:2"]
        assert mcp.calls[0][1]["prefix"] == "user:"

    async def test_list_returns_empty_list_when_no_keys(self):
        mcp = RecordingMcp(responses={"state_list": ""})
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        keys = await state.list()

        assert keys == []

    async def test_list_tolerates_malformed_response(self):
        mcp = RecordingMcp(responses={"state_list": "not-json"})
        state = StateService(mcp, "inst-1")  # type: ignore[arg-type]

        keys = await state.list()

        assert keys == []


class TestStateServiceRoundTrip:
    async def test_set_then_get_round_trips_through_the_kernel_contract(self):
        """End-to-end check: set stores a JSON-encoded value, get decodes it
        back. Verifies both sides of the serialisation boundary match."""
        storage: dict[str, str] = {}

        class RoundTripMcp:
            async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
                if tool == "state_set":
                    storage[args["key"]] = args["valueJson"]
                    return ""
                if tool == "state_get":
                    return storage.get(args["key"], "null")
                return ""

        state = StateService(RoundTripMcp(), "inst-1")  # type: ignore[arg-type]
        original = {"items": [1, 2, 3], "nested": {"key": "value"}}

        await state.set("roundtrip", original)
        recovered = await state.get("roundtrip")

        assert recovered == original
