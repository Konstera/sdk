# Schemas

Published JSON Schemas for Konstera agent authors.

| File | Purpose |
|------|---------|
| `agent-manifest.v3.json` | Schema for an agent's `manifest.json` (JSON Schema 2020-12). |
| `capability-catalog.json` | Catalogue of platform capabilities an agent can call, with their input/output shapes (ADR-013). |

Both files are owned here (ADR-036). The Konstera platform keeps a byte-identical copy and a drift check compares the two, so **change them only by copying the platform's version across in full** — do not hand-edit them here.

Validate a manifest locally:

```bash
pip install jsonschema
python -c "import json,jsonschema; jsonschema.validate(json.load(open('manifest.json')), json.load(open('schemas/agent-manifest.v3.json')))"
```

## Optional manifest blocks

Both blocks below are optional. A manifest without them stays valid and behaves as before.

### `contextRequirements` (ADR-038)

Lists the context names your agent reads at runtime: glossary terms (`ctx.semantic.glossary_lookup`), skills (`ctx.semantic.skills_get`) and ontology entities. When a tenant installs the agent, the platform checks these names against the tenant's Context Service:

- `required` names that are missing **block the install**.
- `recommended` names that are missing only produce a warning. The agent should still work without them, with less detail.

Names are lower snake_case (`^[a-z][a-z0-9_]*$`, max 64 chars). Every section is optional.

```json
"contextRequirements": {
  "glossary":         { "required": ["refund_window"], "recommended": ["vip_tier"] },
  "skills":           { "recommended": ["refund_policy"] },
  "ontologyEntities": { "required": ["customer", "order"] }
}
```

### `eval` (ADR-044)

Opts the agent into the platform's quality-check harness. The harness POSTs each scenario's `input` to `endpoint`, compares the response with `expected`, and reports pass/fail per scenario and per `cluster_tag`. Leave the block out to opt out of evaluation (fine for one-shot connectors or pure data transforms).

- `endpoint` (required): path the harness calls, conventionally `/eval`.
- `mode` (required): `deterministic` (repeatable output, exact match on the `expected` keys; preferred for nightly runs) or `live` (real LLM/connectors, fuzzy comparison).
- `timeoutSeconds`: per-scenario timeout, 1-600, default 30.
- `scenarios`: baseline test cases (`id`, `question`, `expected` required; `cluster_tag` and `input` optional). Keep `id` stable across versions so trend data stays attached. These are synced to the tenant when the agent is installed, and tenants can add their own scenarios in the portal.

```json
"eval": {
  "endpoint": "/eval",
  "mode": "deterministic",
  "timeoutSeconds": 30,
  "scenarios": [
    {
      "id": "refund-standard-1",
      "cluster_tag": "standard_refund",
      "question": "Customer asks for a refund inside the return window",
      "input":    { "message": "I want a refund for order 1001" },
      "expected": { "intent": "refund" }
    }
  ]
}
```
