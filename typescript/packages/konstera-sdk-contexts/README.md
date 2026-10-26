<img src="https://raw.githubusercontent.com/Konstera/sdk/main/assets/brand/konstera-mark-blue.png" alt="Konstera" width="64" />

# @konstera/sdk-contexts

Typed constants for the **Konstera Standard Context Pack v1** — canonical glossary / skill / ontology-entity names that every retail-core seed pack guarantees.

Mirror of `Konstera.Sdk.Contexts` (NuGet) and `konstera-sdk-contexts` (PyPI).

## Why

A Konstera agent's manifest declares `contextRequirements`. If the agent hard-codes those names as magic strings, a typo (`"refund_windows_days"`) means the install-time check silently reports "name missing" and the agent panics at runtime when `ctx.context.glossary.get("refund_windows_days")` returns `undefined`.

Reference the constants instead:

```typescript
import { ContextTerms, ContextSkills, ContextEntities } from "@konstera/sdk-contexts";

const manifest = {
  contextRequirements: {
    glossary: {
      required: [ContextTerms.RefundWindowDays, ContextTerms.VipTierException],
      recommended: [ContextTerms.LimitedEditionRestockingFee],
    },
    skills: {
      required: [ContextSkills.EvaluateRefundEligibility],
    },
    ontologyEntities: {
      required: [ContextEntities.Customer, ContextEntities.Order, ContextEntities.Refund],
    },
  },
};
```

Typos now fail at `tsc`, not at `kns deploy`.

## What's in it

- `ContextTerms` — 24 glossary terms (customer-service, merchandising, supply-chain, finance, general retail)
- `ContextSkills` — 2 reference skills (`EvaluateRefundEligibility`, `DiagnoseMarkdownSpike`)
- `ContextEntities` — 24 ontology entities (customer, order, order_line, sku, product, …)

Each export is a `const object` + inferred literal union types:

```typescript
type ContextTermsKey = keyof typeof ContextTerms;
type ContextTermsValue = (typeof ContextTerms)[ContextTermsKey];
// → "refund_window_days" | "vip_tier_exception" | ...
```

So a function signature `function requireTerm(name: ContextTermsValue)` only accepts canonical wire-level names.

## Raw pack

Need descriptions, domains, canonical units? Import the raw pack JSON:

```typescript
import pack from "@konstera/sdk-contexts/pack.json" assert { type: "json" };
console.log(pack.glossary.refund_window_days.description);
```

## Versioning

- Package version follows the pack version. **Pack v1 → `1.x.x`**.
- Adding names is a non-breaking **minor** bump; removing / renaming a name is **major**.
- Pack v2 (planned finance + HR expansion) ships as `@konstera/sdk-contexts` `2.x.x`.

## License

Apache-2.0.
