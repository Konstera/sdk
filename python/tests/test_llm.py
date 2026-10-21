"""LlmService — provider-agnostic chat completion wrapper.

Covers:
- `complete()` validation (must supply purpose OR model)
- Args serialisation (purpose vs model, system, temperature, max_tokens)
- Invocation ID injection (explicit arg wins over ambient scope)
- Response parsing (LlmResult shape, defaults for missing fields,
  error on empty response)
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from konstera_sdk._invocation_context import enter_invocation
from konstera_sdk.llm import LlmResult, LlmService


class RecordingMcp:
    def __init__(self, response: str = ""):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.response = response

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self.response


def _llm_response_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "content": "Hello!",
        "model": "claude-sonnet-4-6",
        "provider": "anthropic",
        "inputTokens": 10,
        "outputTokens": 5,
        "cachedInputTokens": 0,
        "costUsd": 0.0003,
        "stopReason": "end_turn",
        "purpose": "narrator",
    }
    base.update(overrides)
    return base


class TestValidation:
    async def test_requires_purpose_or_model(self):
        llm = LlmService(RecordingMcp(), "inst-1")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match=r"purpose.*model"):
            await llm.complete(prompt="hi")

    async def test_accepts_purpose_only(self):
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict()))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]
        result = await llm.complete(prompt="hi", purpose="narrator")
        assert isinstance(result, LlmResult)
        assert mcp.calls[0][1]["purpose"] == "narrator"
        assert "model" not in mcp.calls[0][1]

    async def test_accepts_model_only(self):
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict(purpose=None)))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]
        result = await llm.complete(prompt="hi", model="claude-sonnet-4-6")
        assert isinstance(result, LlmResult)
        assert mcp.calls[0][1]["model"] == "claude-sonnet-4-6"
        assert "purpose" not in mcp.calls[0][1]

    async def test_accepts_both_purpose_and_model(self):
        """Not forbidden — kernel decides precedence. SDK forwards both."""
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict()))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]
        await llm.complete(prompt="hi", purpose="narrator", model="override-x")
        args = mcp.calls[0][1]
        assert args["purpose"] == "narrator"
        assert args["model"] == "override-x"


class TestArgsSerialisation:
    async def test_minimal_args_sends_caller_and_prompt(self):
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict()))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]
        await llm.complete(prompt="Explain X.", purpose="narrator")

        args = mcp.calls[0][1]
        assert args["callerInstanceId"] == "inst-1"
        assert args["prompt"] == "Explain X."
        # Omitted optional args should not appear
        assert "system" not in args
        assert "temperature" not in args
        assert "maxTokens" not in args

    async def test_full_args_pass_through(self):
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict()))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]
        await llm.complete(
            prompt="hi",
            purpose="narrator",
            system="You are terse.",
            temperature=0.1,
            max_tokens=256,
        )

        args = mcp.calls[0][1]
        assert args["system"] == "You are terse."
        assert args["temperature"] == 0.1
        assert args["maxTokens"] == 256


class TestInvocationIdInjection:
    async def test_explicit_invocation_id_wins_over_ambient(self):
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict()))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]

        with enter_invocation("ambient-id"):
            await llm.complete(
                prompt="x", purpose="narrator", invocation_id="explicit-id"
            )

        assert mcp.calls[0][1]["invocationId"] == "explicit-id"

    async def test_ambient_invocation_id_used_when_no_explicit(self):
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict()))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]

        with enter_invocation("ambient-id"):
            await llm.complete(prompt="x", purpose="narrator")

        assert mcp.calls[0][1]["invocationId"] == "ambient-id"

    async def test_no_invocation_id_when_neither_set(self):
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict()))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]

        await llm.complete(prompt="x", purpose="narrator")

        assert "invocationId" not in mcp.calls[0][1]


class TestResponseParsing:
    async def test_populates_all_fields(self):
        mcp = RecordingMcp(response=json.dumps(_llm_response_dict()))
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]
        result = await llm.complete(prompt="hi", purpose="narrator")

        assert result.content == "Hello!"
        assert result.model == "claude-sonnet-4-6"
        assert result.provider == "anthropic"
        assert result.input_tokens == 10
        assert result.output_tokens == 5
        assert result.cached_input_tokens == 0
        assert result.cost_usd == pytest.approx(0.0003)
        assert result.stop_reason == "end_turn"
        assert result.purpose == "narrator"

    async def test_handles_missing_optional_fields(self):
        """Minimal response (just content + model + tokens) — defaults
        kick in for the rest. stop_reason + purpose stay None."""
        mcp = RecordingMcp(response='{"content": "hi"}')
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]
        result = await llm.complete(prompt="hi", purpose="narrator")

        assert result.content == "hi"
        assert result.model == ""
        assert result.provider == ""
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.cached_input_tokens == 0
        assert result.cost_usd == 0.0
        assert result.stop_reason is None
        assert result.purpose is None

    async def test_raises_on_empty_response(self):
        """Unlike list-returning services where "" → [] is sensible, llm
        can't do anything with an empty response — raise explicitly."""
        mcp = RecordingMcp(response="")
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]

        with pytest.raises(RuntimeError, match="no result"):
            await llm.complete(prompt="hi", purpose="narrator")

    async def test_cost_coerced_to_float(self):
        """Kernel may send cost as a string; cost should always be float."""
        mcp = RecordingMcp(response='{"content": "x", "costUsd": "0.00123"}')
        llm = LlmService(mcp, "inst-1")  # type: ignore[arg-type]
        result = await llm.complete(prompt="x", purpose="narrator")
        assert isinstance(result.cost_usd, float)
        assert result.cost_usd == pytest.approx(0.00123)


class TestLlmResultDataclass:
    def test_result_is_frozen(self):
        import dataclasses

        r = LlmResult(
            content="x",
            model="m",
            provider="p",
            input_tokens=1,
            output_tokens=1,
            cached_input_tokens=0,
            cost_usd=0.0,
            stop_reason=None,
        )
        try:
            r.content = "mutated"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except dataclasses.FrozenInstanceError:
            pass
