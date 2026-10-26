"""Konstera Python SDK — build agents in ~10 lines.

See README.md for the minimum-viable-agent example. See docs/SPEC.md §7 for
the conceptual model shared with the .NET SDK.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

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
from .types import AgentRequest, AgentResponse
from .vector import VectorHit, VectorService

# Read from the installed distribution so it always matches pyproject.toml
# (a hand-kept literal had drifted to 0.12.0 while 0.6.x was published).
try:
    __version__ = _dist_version("konstera-sdk")
except PackageNotFoundError:  # pragma: no cover - source tree not installed
    __version__ = "0.0.0+unknown"

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
