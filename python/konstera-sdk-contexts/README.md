# konstera-sdk-contexts

Typed constants for the **Konstera Standard Context Pack v1** — canonical glossary / skill / ontology-entity names that every retail-core seed pack guarantees.

Mirror of `Konstera.Sdk.Contexts` (NuGet) and `konstera-sdk-contexts` (npm).

## Why

A Konstera agent's manifest declares `contextRequirements`. If the agent hard-codes those names as magic strings, a typo (`"refund_windows_days"`) means the install-time check silently reports "name missing" and the agent panics at runtime when `ctx.context.glossary.get("refund_windows_days")` returns `None`.

Reference the constants instead:

```python
from konstera_sdk_contexts import ContextTerms, ContextSkills, ContextEntities

manifest["contextRequirements"] = {
    "glossary": {
        "required": [ContextTerms.REFUND_WINDOW_DAYS, ContextTerms.VIP_TIER_EXCEPTION],
        "recommended": [ContextTerms.LIMITED_EDITION_RESTOCKING_FEE],
    },
    "skills": {
        "required": [ContextSkills.EVALUATE_REFUND_ELIGIBILITY],
    },
    "ontologyEntities": {
        "required": [ContextEntities.CUSTOMER, ContextEntities.ORDER, ContextEntities.REFUND],
    },
}
```

Typos now fail at import, not at `kns deploy`.

## What's in it

- `ContextTerms` — 24 glossary terms (customer-service, merchandising, supply-chain, finance, general retail)
- `ContextSkills` — 2 reference skills (`EVALUATE_REFUND_ELIGIBILITY`, `DIAGNOSE_MARKDOWN_SPIKE`)
- `ContextEntities` — 24 ontology entities (customer, order, order_line, sku, product, …)

The raw pack JSON is bundled inside the wheel at `konstera_sdk_contexts/schemas/standard-context-pack-v1.json`. Load it when you need descriptions / domains:

```python
from konstera_sdk_contexts import load_pack

pack = load_pack()
print(pack["glossary"]["refund_window_days"]["description"])
```

## Versioning

- Package version follows the pack version. **Pack v1 → `1.x.x`**.
- Adding names is a non-breaking **minor** bump; removing / renaming a name is **major**.
- Pack v2 (planned finance + HR expansion) ships as `konstera-sdk-contexts` `2.x.x`.

## License

Apache-2.0.
