"""AgentFailure carries a category the runtime puts in the error body."""
from __future__ import annotations

from starlette.testclient import TestClient

from konstera_sdk import Agent, AgentContext, AgentFailure, AgentRequest, AgentResponse
from konstera_sdk._mcp import KernelMcpClient
from konstera_sdk.runtime import build_app


class _Refused(AgentFailure):
    category = AgentFailure.ACTION_NEEDED


class _FailingAgent(Agent):
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        raise self._exc


def _invoke(exc: Exception) -> dict:
    ctx = AgentContext.from_env(KernelMcpClient(None))
    with TestClient(build_app(_FailingAgent(exc), ctx)) as client:
        r = client.post("/invoke", json={"invocationId": "i1", "input": ""})
    assert r.status_code == 500
    return r.json()["error"]


def test_declared_category_is_sent() -> None:
    err = _invoke(AgentFailure("site down", category="dependency_failure"))
    assert err == {"type": "AgentFailure", "message": "site down", "category": "dependency_failure"}


def test_subclass_category_is_sent() -> None:
    assert _invoke(_Refused("fix the connection"))["category"] == "action_needed"


def test_plain_exception_has_no_category() -> None:
    assert "category" not in _invoke(RuntimeError("boom"))


def test_default_category_is_dependency_failure() -> None:
    assert AgentFailure("x").category == "dependency_failure"
