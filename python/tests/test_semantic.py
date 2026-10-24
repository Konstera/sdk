"""SemanticService (ADR-037 M13 W2) — tenant semantic plane access.

Covers all 5 methods (glossary_lookup / glossary_list / ontology_lookup /
skills_get / cluster_pass_rate[s]), the four dataclass from_dict mappers,
and the ADR-039 feature-disabled envelope translation.
"""
from __future__ import annotations

import json
from typing import Any

from konstera_sdk.semantic import (
    ClusterPassRate,
    GlossaryTerm,
    OntologyEntity,
    SemanticService,
    Skill,
    SkillStep,
)


class RecordingMcp:
    def __init__(self, responses: dict[str, str] | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses = responses or {}

    async def call_tool_for_result(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        return self.responses.get(tool, "")


def _glossary_term_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "term-1",
        "name": "revenue",
        "definition": "Net income from sales after returns and discounts.",
        "synonyms": ["net_revenue", "sales"],
        "canonical_unit": "USD",
        "owner_user_id": "user-42",
        "version": 3,
        "status": "active",
        "repository_id": "repo-1",
        "repository_name": "finance",
        "updated_at": "2026-10-20T12:00:00Z",
    }
    base.update(overrides)
    return base


def _ontology_entity_dict(**overrides: Any) -> dict[str, Any]:
    properties = {
        "identity": {
            "primary": {"field": "email", "capability": "customers.lookup_by_email"},
            "fallbacks": [
                {"field": "loyalty_id", "capability": "customers.lookup_by_loyalty_id"},
            ],
        },
        "key_attributes": {
            "vip_tier": {"type": "enum", "values": ["bronze", "silver", "gold"]}
        },
    }
    base = {
        "id": "ent-1",
        "canonical_name": "customer",
        "entity_type": "person",
        "synonyms": ["account", "buyer"],
        "description": "A paying customer identified across vendor backings.",
        "repository_id": "repo-2",
        "repository_name": "retail",
        "properties": json.dumps(properties),
        "source": "starter_template",
        "status": "active",
        "updated_at": "2026-10-20T12:00:00Z",
    }
    base.update(overrides)
    return base


def _skill_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "skill-1",
        "name": "evaluate_refund_eligibility",
        "description": "6-step deterministic playbook for refund decisions.",
        "domain": "cs",
        "agent_binding_mask": ["io.konstera.customer-service-agent"],
        "version": 2,
        "status": "active",
        "repository_id": "repo-3",
        "repository_name": "cs-skills",
        "steps": [
            {
                "step_order": 1,
                "kind": "lookup",
                "description": "Fetch the customer",
                "payload": {"capability": "customers.lookup_by_email"},
            },
            {
                "step_order": 2,
                "kind": "decide",
                "description": "Within refund window?",
                "payload": {"threshold_days": 30},
            },
        ],
    }
    base.update(overrides)
    return base


class TestGlossaryTermFromDict:
    def test_populates_all_fields_from_full_dict(self):
        term = GlossaryTerm.from_dict(_glossary_term_dict())
        assert term.id == "term-1"
        assert term.name == "revenue"
        assert term.synonyms == ["net_revenue", "sales"]
        assert term.canonical_unit == "USD"
        assert term.owner_user_id == "user-42"
        assert term.version == 3

    def test_tolerates_missing_optional_fields(self):
        d = _glossary_term_dict()
        del d["synonyms"]
        del d["canonical_unit"]
        del d["owner_user_id"]
        term = GlossaryTerm.from_dict(d)
        assert term.synonyms == []
        assert term.canonical_unit is None
        assert term.owner_user_id is None


class TestOntologyEntityFromDict:
    def test_parses_properties_json_string(self):
        entity = OntologyEntity.from_dict(_ontology_entity_dict())
        assert entity.canonical_name == "customer"
        # properties string → parsed dict
        assert entity.properties["identity"]["primary"]["field"] == "email"
        assert len(entity.properties["identity"]["fallbacks"]) == 1

    def test_accepts_properties_already_dict(self):
        """Some callers / fixtures pass the parsed dict directly rather than
        a JSON string. Service must accept both."""
        d = _ontology_entity_dict()
        d["properties"] = {"identity": {"primary": {"field": "x"}}}
        entity = OntologyEntity.from_dict(d)
        assert entity.properties["identity"]["primary"]["field"] == "x"

    def test_malformed_properties_json_falls_back_to_empty_dict(self):
        d = _ontology_entity_dict()
        d["properties"] = "not-valid-json{{"
        entity = OntologyEntity.from_dict(d)
        assert entity.properties == {}

    def test_null_properties_falls_back_to_empty(self):
        d = _ontology_entity_dict()
        d["properties"] = None
        entity = OntologyEntity.from_dict(d)
        assert entity.properties == {}


class TestSkillFromDict:
    def test_hydrates_steps_in_declared_order(self):
        skill = Skill.from_dict(_skill_dict())
        assert len(skill.steps) == 2
        assert isinstance(skill.steps[0], SkillStep)
        assert skill.steps[0].step_order == 1
        assert skill.steps[0].kind == "lookup"
        assert skill.steps[1].kind == "decide"

    def test_derives_step_order_from_position_when_missing(self):
        """A step without explicit step_order falls back to its 1-indexed
        position — forward-compatible with payloads that omit the field."""
        d = _skill_dict()
        for s in d["steps"]:
            del s["step_order"]
        skill = Skill.from_dict(d)
        assert skill.steps[0].step_order == 1
        assert skill.steps[1].step_order == 2


class TestClusterPassRateFromDict:
    def test_coerces_numeric_fields(self):
        rate = ClusterPassRate.from_dict(
            {
                "cluster_tag": "refund-eligible",
                "total": "20",  # kernel may send as string from JSON
                "passed": "17",
                "pass_rate": "0.85",
                "run_id": "run-xyz",
                "recorded_at": "2026-10-20T12:00:00Z",
            }
        )
        assert rate.total == 20
        assert rate.passed == 17
        assert rate.pass_rate == 0.85


class TestGlossaryLookup:
    async def test_sends_caller_instance_id_and_term(self):
        mcp = RecordingMcp(
            responses={"context_glossary_lookup": json.dumps(_glossary_term_dict())},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await sem.glossary_lookup("revenue")

        assert result is not None
        assert result.name == "revenue"
        assert mcp.calls == [
            ("context_glossary_lookup", {"callerInstanceId": "inst-1", "term": "revenue"})
        ]

    async def test_returns_none_for_empty_response(self):
        mcp = RecordingMcp(responses={"context_glossary_lookup": ""})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_lookup("unknown") is None

    async def test_returns_none_for_null_response(self):
        mcp = RecordingMcp(responses={"context_glossary_lookup": "null"})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_lookup("unknown") is None

    async def test_feature_disabled_envelope_returns_none(self):
        envelope = {
            "status": "feature_disabled",
            "feature": "context_service",
            "upgrade_hint": "Enable in Settings → Features.",
        }
        mcp = RecordingMcp(
            responses={"context_glossary_lookup": json.dumps(envelope)},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_lookup("revenue") is None


class TestGlossaryLookupById:
    async def test_sends_caller_instance_id_and_id(self):
        mcp = RecordingMcp(
            responses={
                "context_glossary_lookup_by_id": json.dumps(_glossary_term_dict(id="term-xyz")),
            },
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await sem.glossary_lookup_by_id("term-xyz")

        assert result is not None
        assert result.id == "term-xyz"
        assert mcp.calls == [
            ("context_glossary_lookup_by_id", {"callerInstanceId": "inst-1", "id": "term-xyz"})
        ]

    async def test_returns_none_for_empty_response(self):
        mcp = RecordingMcp(responses={"context_glossary_lookup_by_id": ""})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_lookup_by_id("missing-id") is None

    async def test_returns_none_for_null_response(self):
        mcp = RecordingMcp(responses={"context_glossary_lookup_by_id": "null"})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_lookup_by_id("missing-id") is None

    async def test_feature_disabled_envelope_returns_none(self):
        envelope = {
            "status": "feature_disabled",
            "feature": "context_service",
            "upgrade_hint": "Enable in Settings → Features.",
        }
        mcp = RecordingMcp(
            responses={"context_glossary_lookup_by_id": json.dumps(envelope)},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_lookup_by_id("term-xyz") is None


class TestGlossaryList:
    async def test_lists_without_domain_filter(self):
        terms = [_glossary_term_dict(id=f"t-{i}", name=f"term_{i}") for i in range(3)]
        mcp = RecordingMcp(
            responses={"context_glossary_list": json.dumps(terms)},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        result = await sem.glossary_list()

        assert len(result) == 3
        assert all(isinstance(t, GlossaryTerm) for t in result)
        # No domain in args when None
        assert "domain" not in mcp.calls[0][1]

    async def test_lists_with_domain_filter(self):
        mcp = RecordingMcp(responses={"context_glossary_list": "[]"})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        await sem.glossary_list(domain="cs")

        assert mcp.calls[0][1]["domain"] == "cs"

    async def test_feature_disabled_envelope_returns_empty_list(self):
        envelope = {"status": "feature_disabled", "feature": "context_service"}
        mcp = RecordingMcp(
            responses={"context_glossary_list": json.dumps(envelope)},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_list() == []

    async def test_non_list_response_returns_empty(self):
        mcp = RecordingMcp(responses={"context_glossary_list": '{"not": "a list"}'})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_list() == []

    async def test_empty_response_returns_empty_list(self):
        mcp = RecordingMcp(responses={"context_glossary_list": ""})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.glossary_list() == []


class TestOntologyLookup:
    async def test_returns_entity_with_parsed_properties(self):
        mcp = RecordingMcp(
            responses={"context_ontology_resolve": json.dumps(_ontology_entity_dict())},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        entity = await sem.ontology_lookup("customer")

        assert entity is not None
        assert entity.canonical_name == "customer"
        assert entity.properties["identity"]["primary"]["field"] == "email"

    async def test_returns_none_for_unknown(self):
        mcp = RecordingMcp(responses={"context_ontology_resolve": "null"})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.ontology_lookup("alien") is None

    async def test_feature_disabled_envelope_returns_none(self):
        envelope = {"status": "feature_disabled", "feature": "context_service"}
        mcp = RecordingMcp(
            responses={"context_ontology_resolve": json.dumps(envelope)},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.ontology_lookup("customer") is None

    async def test_sends_entity_name(self):
        mcp = RecordingMcp(responses={"context_ontology_resolve": "null"})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        await sem.ontology_lookup("customer")
        assert mcp.calls[0][1]["entityName"] == "customer"


class TestSkillsGet:
    async def test_returns_skill_with_hydrated_steps(self):
        mcp = RecordingMcp(
            responses={"context_skills_get": json.dumps(_skill_dict())},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        skill = await sem.skills_get("evaluate_refund_eligibility")

        assert skill is not None
        assert skill.name == "evaluate_refund_eligibility"
        assert len(skill.steps) == 2
        assert skill.steps[0].kind == "lookup"

    async def test_returns_none_for_unknown_skill(self):
        mcp = RecordingMcp(responses={"context_skills_get": "null"})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.skills_get("made_up_skill") is None

    async def test_feature_disabled_envelope_returns_none(self):
        envelope = {"status": "feature_disabled", "feature": "context_service"}
        mcp = RecordingMcp(
            responses={"context_skills_get": json.dumps(envelope)},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.skills_get("evaluate_refund_eligibility") is None


class TestClusterPassRates:
    async def test_returns_map_keyed_by_cluster_tag(self):
        payload = {
            "refund-eligible": {
                "cluster_tag": "refund-eligible",
                "total": 20,
                "passed": 17,
                "pass_rate": 0.85,
                "run_id": "run-1",
                "recorded_at": "2026-10-20T12:00:00Z",
            },
            "refund-ineligible": {
                "cluster_tag": "refund-ineligible",
                "total": 10,
                "passed": 10,
                "pass_rate": 1.0,
                "run_id": "run-1",
                "recorded_at": "2026-10-20T12:00:00Z",
            },
        }
        mcp = RecordingMcp(
            responses={
                "context_evaluation_cluster_pass_rates": json.dumps(payload),
            },
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        rates = await sem.cluster_pass_rates("agent-package-id")

        assert set(rates.keys()) == {"refund-eligible", "refund-ineligible"}
        assert rates["refund-eligible"].pass_rate == 0.85
        assert rates["refund-ineligible"].passed == 10

    async def test_empty_response_returns_empty_dict(self):
        mcp = RecordingMcp(responses={"context_evaluation_cluster_pass_rates": ""})
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.cluster_pass_rates("agent-id") == {}

    async def test_feature_disabled_envelope_returns_empty_dict(self):
        envelope = {"status": "feature_disabled", "feature": "context_service"}
        mcp = RecordingMcp(
            responses={
                "context_evaluation_cluster_pass_rates": json.dumps(envelope),
            },
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.cluster_pass_rates("agent-id") == {}

    async def test_non_dict_response_returns_empty(self):
        mcp = RecordingMcp(
            responses={"context_evaluation_cluster_pass_rates": "[1, 2, 3]"},
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]
        assert await sem.cluster_pass_rates("agent-id") == {}


class TestClusterPassRateSingular:
    async def test_returns_single_cluster_from_map(self):
        payload = {
            "refund-eligible": {
                "cluster_tag": "refund-eligible",
                "total": 20,
                "passed": 17,
                "pass_rate": 0.85,
                "run_id": "run-1",
                "recorded_at": "2026-10-20T12:00:00Z",
            },
        }
        mcp = RecordingMcp(
            responses={
                "context_evaluation_cluster_pass_rates": json.dumps(payload),
            },
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        rate = await sem.cluster_pass_rate("agent-id", "refund-eligible")

        assert rate is not None
        assert rate.pass_rate == 0.85

    async def test_returns_none_for_unknown_cluster(self):
        payload = {
            "refund-eligible": {
                "cluster_tag": "refund-eligible",
                "total": 1,
                "passed": 1,
                "pass_rate": 1.0,
                "run_id": "r",
                "recorded_at": "t",
            }
        }
        mcp = RecordingMcp(
            responses={
                "context_evaluation_cluster_pass_rates": json.dumps(payload),
            },
        )
        sem = SemanticService(mcp, "inst-1")  # type: ignore[arg-type]

        rate = await sem.cluster_pass_rate("agent-id", "nonexistent-cluster")

        assert rate is None
