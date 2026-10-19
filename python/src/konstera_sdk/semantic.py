"""SemanticService — tenant semantic plane access for agents (ADR-037).

Exposes the kernel ContextService via MCP so agents can read:
  - glossary terms (business definitions)
  - ontology entities (planned)
  - skills (named reusable playbooks with ordered steps)
  - semantic bindings (glossary term → data location)

The service does not include write operations — glossary/ontology/skill
edits happen through the portal admin surface, not from agents.

Shape mirrors the kernel-side DTOs in Konstera.Kernel.Context.ContextTypes.
Field names are snake_case on the wire so no mapper layer is needed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ._mcp import KernelMcpClient


@dataclass(slots=True, frozen=True)
class GlossaryTerm:
    """A business term definition — the authoritative meaning of e.g. 'revenue'
    for this tenant. Returned by SemanticService.glossary_lookup / .glossary_list."""

    id: str
    name: str
    definition: str
    synonyms: list[str]
    canonical_unit: str | None
    owner_user_id: str | None
    version: int
    status: str
    repository_id: str
    repository_name: str
    updated_at: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GlossaryTerm":
        return cls(
            id=str(d["id"]),
            name=str(d["name"]),
            definition=str(d["definition"]),
            synonyms=list(d.get("synonyms") or []),
            canonical_unit=d.get("canonical_unit"),
            owner_user_id=d.get("owner_user_id"),
            version=int(d.get("version", 1)),
            status=str(d.get("status", "active")),
            repository_id=str(d["repository_id"]),
            repository_name=str(d["repository_name"]),
            updated_at=str(d["updated_at"]),
        )


@dataclass(slots=True, frozen=True)
class OntologyEntity:
    """A business entity from the tenant ontology (ADR-037 Step 3.5 B.2).

    Returned by SemanticService.ontology_lookup. The `properties` field
    is the full JSONB blob stored for the entity — tenant-authored and
    intentionally not strongly typed, since different entities carry
    different shapes (customer has `identity` + `key_attributes`; order
    may carry lifecycle status enums; product may carry supplier bindings).

    Agents parse `properties` themselves. For the customer entity under
    the thin-semantic model (migration 115), the shape is:

        {
          "identity": {
            "primary":   {"field": "...", "capability": "..."},
            "fallbacks": [{"field": "...", "capability": "..."}, ...]
          },
          "key_attributes": {
            "<name>": {"type": "enum|number|datetime|...", "values": [...], ...}
          }
        }

    See wiki/concepts/ontology.md for the full worked scenario.
    """

    id: str
    canonical_name: str
    entity_type: str
    synonyms: list[str]
    description: str | None
    repository_id: str
    repository_name: str
    properties: dict[str, Any]      # Parsed JSON from the kernel's string field
    source: str                     # starter_template | authored | external_catalog
    status: str                     # active | archived
    updated_at: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OntologyEntity":
        # Kernel ships `properties` as a JSON *string* (OntologyEntityView
        # PropertiesJson in Konstera.Kernel.Context.ContextTypes). Parse
        # here so agent code reads nested shapes directly without a double
        # json.loads at every call site.
        raw_props = d.get("properties") or "{}"
        if isinstance(raw_props, str):
            try:
                parsed_props: dict[str, Any] = json.loads(raw_props)
            except json.JSONDecodeError:
                parsed_props = {}
        elif isinstance(raw_props, dict):
            parsed_props = raw_props
        else:
            parsed_props = {}

        return cls(
            id=str(d["id"]),
            canonical_name=str(d["canonical_name"]),
            entity_type=str(d["entity_type"]),
            synonyms=list(d.get("synonyms") or []),
            description=d.get("description"),
            repository_id=str(d["repository_id"]),
            repository_name=str(d["repository_name"]),
            properties=parsed_props,
            source=str(d.get("source", "authored")),
            status=str(d.get("status", "active")),
            updated_at=str(d["updated_at"]),
        )


@dataclass(slots=True, frozen=True)
class SkillStep:
    """One step of a Skill playbook. `payload` is passed through verbatim —
    the shape depends on `kind` (lookup / decide / action / invoke_capability).
    See migration 092 for the authoritative shape per kind."""

    step_order: int
    kind: str
    description: str | None
    payload: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ClusterPassRate:
    """Per-cluster pass-rate snapshot from the most recent harness run
    (ADR-037 M13 W3-B). Consumed by the cluster-aware autopilot gate.

    `pass_rate` is in [0.0, 1.0]. `total` is included so a sample size of 1
    doesn't look as authoritative as 10 — a future gate ADR may require a
    minimum `total` before trusting the rate."""

    cluster_tag: str
    total: int
    passed: int
    pass_rate: float
    run_id: str
    recorded_at: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClusterPassRate":
        return cls(
            cluster_tag=str(d["cluster_tag"]),
            total=int(d["total"]),
            passed=int(d["passed"]),
            pass_rate=float(d["pass_rate"]),
            run_id=str(d["run_id"]),
            recorded_at=str(d["recorded_at"]),
        )


@dataclass(slots=True, frozen=True)
class Skill:
    """A named reusable playbook, as returned by SemanticService.skills_get.
    Steps are ordered by step_order ascending."""

    id: str
    name: str
    description: str | None
    domain: str
    agent_binding_mask: list[str]
    version: int
    status: str
    repository_id: str
    repository_name: str
    steps: list[SkillStep]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Skill":
        return cls(
            id=str(d["id"]),
            name=str(d["name"]),
            description=d.get("description"),
            domain=str(d.get("domain", "general")),
            agent_binding_mask=list(d.get("agent_binding_mask") or []),
            version=int(d.get("version", 1)),
            status=str(d.get("status", "active")),
            repository_id=str(d["repository_id"]),
            repository_name=str(d["repository_name"]),
            steps=[
                SkillStep(
                    step_order=int(s.get("step_order", i + 1)),
                    kind=str(s["kind"]),
                    description=s.get("description"),
                    payload=s.get("payload") or {},
                )
                for i, s in enumerate(d.get("steps") or [])
            ],
        )


class SemanticService:
    """Agent-side wrapper over the kernel ContextService (ADR-037 M13 W2).

    Methods:
      - glossary_lookup(term) → GlossaryTerm | None
      - glossary_list(domain=None) → list[GlossaryTerm]
      - ontology_lookup(entity_name) → OntologyEntity | None
      - skills_get(name) → Skill | None
      - cluster_pass_rate(agent_id, cluster_tag) → ClusterPassRate | None

    Caller instance UUID is injected automatically on every call.

    Feature-toggle degradation (ADR-039): when the tenant has
    Context Service disabled, the kernel returns a
    {status: "feature_disabled", feature: ..., upgrade_hint: ...}
    envelope. The SDK translates that into the method's natural
    "nothing to return" shape (None for lookups, [] for lists) so
    agents can branch on the normal data-availability path without
    special-casing. feature_disabled is logged once per method call
    at INFO level so operators can see when a toggle is suppressing
    traffic — no exceptions raised.
    """

    def __init__(self, mcp: KernelMcpClient, instance_id: str):
        self._mcp = mcp
        self._instance = instance_id

    async def glossary_lookup(self, term: str) -> GlossaryTerm | None:
        """Look up a term by case-insensitive name match, with synonym fallback.
        Returns None if the term is unknown to this tenant or the Context
        Service feature is disabled."""
        raw = await self._mcp.call_tool_for_result(
            "context_glossary_lookup",
            {"callerInstanceId": self._instance, "term": term},
        )
        if not raw or raw == "null":
            return None
        data = json.loads(raw)
        if _is_feature_disabled(data, method="context_glossary_lookup"):
            return None
        return GlossaryTerm.from_dict(data)

    async def glossary_list(self, domain: str | None = None) -> list[GlossaryTerm]:
        """List active glossary terms, optionally filtered by domain
        (cs | merch | supply_chain | finance | general). Returns [] when
        the Context Service feature is disabled."""
        args: dict[str, Any] = {"callerInstanceId": self._instance}
        if domain is not None:
            args["domain"] = domain
        raw = await self._mcp.call_tool_for_result("context_glossary_list", args)
        if not raw:
            return []
        data = json.loads(raw)
        if _is_feature_disabled(data, method="context_glossary_list"):
            return []
        if not isinstance(data, list):
            return []
        return [GlossaryTerm.from_dict(t) for t in data]

    async def ontology_lookup(self, entity_name: str) -> OntologyEntity | None:
        """Look up a business entity by case-insensitive name match, with
        synonym fallback. Returns None if the entity is unknown to this
        tenant or the Context Service feature is disabled.

        The returned entity's `properties` dict is parsed JSON — for the
        customer entity under the thin-semantic model (migration 115) it
        carries `identity.primary` + `identity.fallbacks[]` + `key_attributes`.
        See wiki/concepts/ontology.md §Worked scenario for how agents
        iterate the identity list to resolve a customer across any backing
        vendor the operator has bound.
        """
        raw = await self._mcp.call_tool_for_result(
            "context_ontology_resolve",
            {"callerInstanceId": self._instance, "entityName": entity_name},
        )
        if not raw or raw == "null":
            return None
        data = json.loads(raw)
        if _is_feature_disabled(data, method="context_ontology_resolve"):
            return None
        return OntologyEntity.from_dict(data)

    async def skills_get(self, name: str) -> Skill | None:
        """Fetch a skill by name with its ordered steps hydrated. Returns
        None if the skill is unknown, archived, or the Context Service
        feature is disabled."""
        raw = await self._mcp.call_tool_for_result(
            "context_skills_get",
            {"callerInstanceId": self._instance, "skillName": name},
        )
        if not raw or raw == "null":
            return None
        data = json.loads(raw)
        if _is_feature_disabled(data, method="context_skills_get"):
            return None
        return Skill.from_dict(data)

    async def cluster_pass_rates(self, agent_id: str) -> dict[str, ClusterPassRate]:
        """Return per-cluster pass rates from the most recent harness run
        for an agent (ADR-037 M13 W3-B).

        agent_id is the agent *package* UUID — the id recorded on
        tenant_context_evaluation.agent_id when the goldens were seeded,
        not an instance id. Pass the ticket-handling agent's package id
        (see tenant_agent_instances.agent_id ↔ agent_packages.agent_id).

        Returns an empty dict when no eval runs exist yet, when the
        agent_id is unknown, or when the Context Service feature is
        disabled for this tenant."""
        raw = await self._mcp.call_tool_for_result(
            "context_evaluation_cluster_pass_rates",
            {"callerInstanceId": self._instance, "agentId": agent_id},
        )
        if not raw:
            return {}
        data = json.loads(raw)
        if _is_feature_disabled(data, method="context_evaluation_cluster_pass_rates"):
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: ClusterPassRate.from_dict(v) for k, v in data.items()}

    async def cluster_pass_rate(
        self, agent_id: str, cluster_tag: str,
    ) -> ClusterPassRate | None:
        """Return the pass-rate snapshot for ONE cluster — the shape the
        autopilot gate consumes. Thin wrapper over cluster_pass_rates:
        the kernel still fetches the full map (one DB round-trip either
        way) but the caller gets exactly the key it asked for, or None
        if that cluster has no eval data yet."""
        m = await self.cluster_pass_rates(agent_id)
        return m.get(cluster_tag)


# ─── module-private helpers ──────────────────────────────────────────

import logging  # local import — only this helper needs the logger

_log = logging.getLogger(__name__)


def _is_feature_disabled(data: Any, *, method: str) -> bool:
    """Recognise the ADR-039 feature-disabled envelope. Returns True (and
    logs once at INFO) when the response is the sentinel shape. Any other
    dict/list/scalar passes through for normal parsing."""
    if isinstance(data, dict) and data.get("status") == "feature_disabled":
        _log.info(
            "%s suppressed — feature %r disabled for this tenant (hint: %s)",
            method,
            data.get("feature", "?"),
            data.get("upgrade_hint", ""),
        )
        return True
    return False
