# Konstera.Sdk.Contexts

Typed constants for the **Konstera Standard Context Pack v1** — the canonical glossary / skill / ontology-entity names that every retail-core seed pack guarantees.

## Why

A Konstera agent's manifest declares `contextRequirements` — glossary terms, skills, and ontology entities the agent assumes exist on the tenant's active context repo. If the agent hard-codes those names as strings, a one-character typo (`"refund_windows_days"`) means the install-time check silently passes (the string is "missing" either way) but the agent panics at runtime when `ctx.context.glossary.get("refund_windows_days")` returns `null`.

Reference the constants in this package instead:

```csharp
using Konstera.Sdk.Contexts;

var manifest = new AgentManifest
{
    ContextRequirements = new ContextRequirements
    {
        Glossary = new ContextRequirementsSection
        {
            Required = { ContextTerms.RefundWindowDays, ContextTerms.VipTierException },
            Recommended = { ContextTerms.LimitedEditionRestockingFee },
        },
        Skills = new ContextRequirementsSection
        {
            Required = { ContextSkills.EvaluateRefundEligibility },
        },
        OntologyEntities = new ContextRequirementsSection
        {
            Required = { ContextEntities.Customer, ContextEntities.Order, ContextEntities.Refund },
        },
    },
};
```

Typos now fail at `dotnet build`, not at `kns deploy`.

## What's in it

- `ContextTerms` — 24 glossary terms across customer-service, merchandising, supply-chain, finance, and general retail
- `ContextSkills` — 2 reference skills (`EvaluateRefundEligibility`, `DiagnoseMarkdownSpike`)
- `ContextEntities` — 24 ontology entities (customer, order, order_line, SKU, product, …)

The raw `standard-context-pack-v1.json` ships inside the NuGet package at `content/schemas/standard-context-pack-v1.json` for consumers that need the descriptions or domain metadata at runtime.

## Versioning

- Package version follows the pack version. **Pack v1 → `1.x.x`**.
- Adding names is a non-breaking **minor** bump; removing or renaming a name is a **major** bump.
- Pack v2 (planned: finance + HR expansion) will ship as `Konstera.Sdk.Contexts` `2.x.x` and vendor a new `standard-context-pack-v2.json`.

## License

Apache-2.0.
