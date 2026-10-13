"""Konstera Python SDK — build agents in ~10 lines.

See README.md for the minimum-viable-agent example. See docs/SPEC.md §7 for
the conceptual model shared with the .NET SDK.
"""
from __future__ import annotations

from .agent import Agent
from .agents import AgentInvokeResult, AgentsService
from .artifact import (
    ArtifactListItem,
    ArtifactService,
    GetResult as ArtifactGetResult,
    HeadResult as ArtifactHeadResult,
    PutResult as ArtifactPutResult,
)
from .capability import (
    CapabilityError,
    CapabilityService,
    CapabilityUnbound,
    CapabilityUpstreamFailed,
)
from .connector import ConnectorGrant, ConnectorService
from .context import AgentContext
from .cost import CostService
from .credentials import CredentialsService
from .human import HumanDecision, HumanService
from .llm import LlmResult, LlmService
from .logging import LogService
from .rule import Rule, RuleService, RuleSummary
from .runtime import run
from .semantic import ClusterPassRate, GlossaryTerm, SemanticService, Skill, SkillStep
from .state import StateService
from .tool import ToolService
from .types import AgentRequest, AgentResponse
from .vector import VectorHit, VectorService

__version__ = "0.11.0"  # ADR-037 M13 W3-B — ctx.semantic.cluster_pass_rate[s] for the cluster-aware autopilot gate

__all__ = [
    "Agent",
    "AgentContext",
    "AgentGetResult",
    "AgentInvokeResult",
    "AgentRequest",
    "AgentResponse",
    "AgentsService",
    "ArtifactGetResult",
    "ArtifactHeadResult",
    "ArtifactListItem",
    "ArtifactPutResult",
    "ArtifactService",
    "CapabilityError",
    "CapabilityService",
    "CapabilityUnbound",
    "CapabilityUpstreamFailed",
    "ClusterPassRate",
    "ConnectorGrant",
    "ConnectorService",
    "CostService",
    "CredentialsService",
    "GlossaryTerm",
    "HumanDecision",
    "HumanService",
    "LlmResult",
    "LlmService",
    "LogService",
    "Rule",
    "RuleService",
    "RuleSummary",
    "SemanticService",
    "Skill",
    "SkillStep",
    "StateService",
    "ToolService",
    "VectorHit",
    "VectorService",
    "run",
    "__version__",
]

# Legacy alias (safety net) — was referenced during design but never public.
AgentGetResult = ArtifactGetResult
