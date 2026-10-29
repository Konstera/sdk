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
)
from .artifact import (
    GetResult as ArtifactGetResult,
)
from .artifact import (
    HeadResult as ArtifactHeadResult,
)
from .artifact import (
    PutResult as ArtifactPutResult,
)
from .browser import BrowserService, BrowserSession
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
from .semantic import (
    ClusterPassRate,
    GlossaryTerm,
    OntologyEntity,
    SemanticService,
    Skill,
    SkillStep,
)
from .state import StateService
from .tool import ToolService
from .types import AgentFailure, AgentRequest, AgentResponse
from .vector import VectorHit, VectorService

__version__ = "0.12.0"  # ADR-037 Step 3.5 B.2 — ctx.semantic.ontology_lookup() + OntologyEntity

__all__ = [
    "Agent",
    "AgentContext",
    "AgentFailure",
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
    "BrowserService",
    "BrowserSession",
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
    "OntologyEntity",
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
    "__version__",
    "run",
]

# Legacy alias (safety net) — was referenced during design but never public.
AgentGetResult = ArtifactGetResult
