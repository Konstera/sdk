"""Minimal Konstera Python agent — the reference target for the SDK's shape.

Run with either:
    python examples/hello.py              # direct-run mode (no kernel needed)
    docker + Konstera stack                # normal mode (kernel injects env)

Then POST to http://localhost:8080/invoke with:
    { "invocationId": "test-1", "input": "world" }
"""
from __future__ import annotations

from konstera_sdk import Agent, AgentContext, AgentRequest, AgentResponse, run


class HelloAgent(Agent):
    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        name = req.input.strip() or "world"
        await ctx.log.info(
            f"Hello, {name}!",
            invocation_id=req.invocation_id,
            input=name,
            language="python",
        )
        return AgentResponse(
            content=f"Hello, {name}! From konstera-sdk example (invocation {req.invocation_id}).",
        )


if __name__ == "__main__":
    run(HelloAgent())
