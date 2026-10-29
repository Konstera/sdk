"""AgentContext — the object passed to every agent method.

Gives the agent access to identity + kernel services, without requiring
the agent to know anything about how those services are wired.
"""
from __future__ import annotations

from dataclasses import dataclass

from ._mcp import KernelMcpClient
from .agents import AgentsService
from .artifact import ArtifactService
from .browser import BrowserService
from .capability import CapabilityService
from .connector import ConnectorService
from .cost import CostService
from .credentials import CredentialsService
from .human import HumanService
from .llm import LlmService
from .logging import LogService
from .rule import RuleService
from .semantic import SemanticService
from .state import StateService
from .tool import ToolService
from .vector import VectorService


@dataclass(slots=True)
class AgentContext:
    """Identity + kernel services passed to every agent method.

    An agent gets `ctx` as the second argument to `initialize()`, `handle()`,
    and `shutdown()`. All kernel-side side effects (logging, LLM calls,
    state writes, vector queries, approvals, etc.) go through properties on
    this object. The agent never configures transport, auth, or credentials
    directly — they're resolved kernel-side from the tenant's bindings.

    Example:
        >>> # Inside handle(req, ctx):
        >>> await ctx.log.info("processing", input=req.input)
        >>> result = await ctx.llm.complete(prompt=req.input, purpose="narrator")
        >>> await ctx.state.set("last_run", {"at": time.time(), "model": result.model})
        >>> if await ctx.capability.available("tickets.reply"):
        ...     await ctx.capability.call("tickets.reply", ticket_id="t-1", body=result.content)
    """

    instance_id: str
    """This agent instance's UUID. Injected by the kernel at container-create
    time via `KONSTERA_AGENT_INSTANCE_ID`. In direct-run mode defaults to
    the sentinel `"unknown-instance"`."""

    tenant_id: str
    """The tenant this instance runs under (M8). UUID as string. Injected by
    the kernel at container-create time via `KONSTERA_TENANT_ID`. Rarely
    needed directly — the kernel scopes every service call by the caller's
    instance ID and resolves the tenant server-side."""

    agent_id: str
    """The agent's manifest-declared id (e.g. `"io.konstera.hello-world-python"`).
    Useful in log messages for cross-agent correlation."""

    agent_version: str
    """The agent's manifest-declared version (e.g. `"0.5.0"`). Shows up in
    `/health` + `/describe` responses so operators can verify what's deployed."""

    # Kernel services — one property per capability.
    log: LogService
    llm: LlmService
    state: StateService          # M7a
    vector: VectorService        # M7a
    credentials: CredentialsService  # M7a
    cost: CostService            # M7a
    tool: ToolService            # M7a
    agents: AgentsService        # M7a
    artifact: ArtifactService    # M7b
    human: HumanService          # M7c
    rule: RuleService            # M7d
    connector: ConnectorService  # ADR-009
    capability: CapabilityService  # ADR-013 — purpose-first indirection over connectors
    semantic: SemanticService    # ADR-037 — tenant semantic plane (glossary / skills / ontology)
    browser: BrowserService      # kernel-hosted browser sessions over a granted connection

    @classmethod
    def from_env(cls, mcp: KernelMcpClient, defaults: dict[str, str] | None = None) -> AgentContext:
        """Build a context from the env vars the kernel injects at
        container-create time. Missing values fall back to unknowns
        rather than raising — an agent should be able to boot in
        direct-run mode with nothing set, and only kernel-callback
        features degrade."""
        import os

        d = defaults or {}
        instance_id = os.getenv(
            "KONSTERA_AGENT_INSTANCE_ID", d.get("instance_id", "unknown-instance")
        )
        # M8: kernel injects KONSTERA_TENANT_ID when it spawns the container.
        # Direct-run mode falls back to a sentinel-looking placeholder string
        # so agents can be booted locally without a kernel.
        tenant_id = os.getenv(
            "KONSTERA_TENANT_ID", d.get("tenant_id", "00000000-0000-0000-0000-000000000000")
        )
        agent_id = os.getenv("KONSTERA_AGENT_ID", d.get("agent_id", "unknown-agent"))
        agent_version = os.getenv("KONSTERA_AGENT_VERSION", d.get("agent_version", "0.0.0"))

        return cls(
            instance_id=instance_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_version=agent_version,
            log=LogService(mcp, instance_id),
            llm=LlmService(mcp, instance_id),
            state=StateService(mcp, instance_id),
            vector=VectorService(mcp, instance_id),
            credentials=CredentialsService(mcp, instance_id),
            cost=CostService(mcp, instance_id),
            tool=ToolService(mcp),
            agents=AgentsService(mcp, instance_id),
            artifact=ArtifactService(mcp, instance_id),
            human=HumanService(mcp, instance_id),
            rule=RuleService(mcp, instance_id),
            connector=ConnectorService(mcp, instance_id),
            capability=CapabilityService(mcp, instance_id),
            semantic=SemanticService(mcp, instance_id),
            browser=BrowserService(mcp, instance_id),
        )
