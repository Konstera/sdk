// Konstera Standard Context Pack v1 — typed constants (TypeScript).
//
// Mirror of Konstera.Sdk.Contexts (NuGet) and konstera-sdk-contexts (PyPI);
// published to npm as @konstera/sdk-contexts.
//
// Reference canonical names so a typo fails at `tsc`, not at install:
//
//   import { ContextTerms, ContextSkills, ContextEntities } from "@konstera/sdk-contexts";
//
//   const manifest = {
//     contextRequirements: {
//       glossary: {
//         required: [ContextTerms.RefundWindowDays, ContextTerms.VipTierException],
//         recommended: [ContextTerms.LimitedEditionRestockingFee],
//       },
//       skills: { required: [ContextSkills.EvaluateRefundEligibility] },
//       ontologyEntities: {
//         required: [ContextEntities.Customer, ContextEntities.Order, ContextEntities.Refund],
//       },
//     },
//   };
//
// The raw pack JSON (descriptions, domains, canonical units) is also exported
// — load it when you need the metadata, not just names.

export {
  ContextEntities,
  ContextSkills,
  ContextTerms,
  type ContextEntitiesKey,
  type ContextEntitiesValue,
  type ContextSkillsKey,
  type ContextSkillsValue,
  type ContextTermsKey,
  type ContextTermsValue,
} from "./generated.js";

export const PACK_VERSION = "v1" as const;
// Keep in step with package.json "version"; sdk-check fails the build if they differ.
export const PACKAGE_VERSION = "1.0.3" as const;
