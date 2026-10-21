// Generated from sdk/schemas/standard-context-pack-v1.json
// by sdk/scripts/generate_constants.py — do not edit by hand.

/**
 * Canonical glossary names in the Konstera Standard Context Pack v1. Reference these as manifest contextRequirements.
 */
export const ContextTerms = {
  /** Average handle time per ticket, including hold + after-call work. */
  Aht: "aht",
  /** Customer acquisition cost — blended cost to acquire a new paying customer. */
  Cac: "cac",
  /** Boolean on a ticket indicating the customer has initiated a chargeback dispute with their card issuer. Blocks the refund path. */
  ChargebackFiled: "chargeback_filed",
  /** Cost of goods sold — landed cost of the units that generated the revenue in the period. */
  Cogs: "cogs",
  /** Customer satisfaction score, 1-5, captured post-ticket. */
  Csat: "csat",
  /** Number of days of expected sell-through covered by current on-hand inventory. */
  DaysCover: "days_cover",
  /** Share of inquiries resolved without human agent contact. Measures self-service effectiveness. */
  DeflectionRate: "deflection_rate",
  /** Contracted delivery service-level agreement — ship-to-doorstep in days by delivery_tier. */
  DeliverySla: "delivery_sla",
  /** First-contact resolution rate — share of tickets resolved on the first customer interaction. */
  Fcr: "fcr",
  /** Current state of an order_line in the pick-pack-ship-deliver lifecycle: pending | picked | packed | shipped | out_for_delivery | delivered | failed. */
  FulfilmentStatus: "fulfilment_status",
  /** Gross margin return on inventory investment — gross margin ÷ average inventory cost. */
  Gmroi: "gmroi",
  /** (Revenue - COGS) ÷ Revenue. */
  GrossMargin: "gross_margin",
  /** Percentage deducted from refund_amount when the returned SKU is limited_edition. Default 15%. */
  LimitedEditionRestockingFee: "limited_edition_restocking_fee",
  /** Customer lifetime value — predicted total revenue a customer generates over their relationship. */
  Ltv: "ltv",
  /** realised-markdown-dollars ÷ gross-sales-dollars. The canonical merchandising KPI for discount depth. */
  MarkdownRate: "markdown_rate",
  /** Open-to-buy — planned receipts budget available for the balance of a period. */
  Otb: "otb",
  /** Degree to which a promotional discount shifts sales within the catalog without generating incremental revenue. */
  PromoCannibalisation: "promo_cannibalisation",
  /** Number of days from delivery during which a return is accepted at full value under the standard policy. */
  RefundWindowDays: "refund_window_days",
  /** Enum reason the customer gave for the return: size | changed_mind | wrong_item | not_as_described | damaged | quality | late_delivery | other. */
  ReturnReasonCode: "return_reason_code",
  /** GAAP revenue excluding returns, net of discounts. The authoritative top-line figure. */
  Revenue: "revenue",
  /** Buffer inventory held to cover demand variability + supplier lead-time variance. */
  SafetyStock: "safety_stock",
  /** Units sold ÷ units received, measured over a season or window. */
  SellThrough: "sell_through",
  /** Loyalty tier assigned to a customer: silver | gold | platinum, with escalating policy exceptions. */
  VipTier: "vip_tier",
  /** Policy clause that extends refund_window_days for customers in a VIP tier and may waive restocking_fee. */
  VipTierException: "vip_tier_exception",
} as const;
export type ContextTermsKey = keyof typeof ContextTerms;
export type ContextTermsValue = (typeof ContextTerms)[ContextTermsKey];

/**
 * Canonical skill names in the Konstera Standard Context Pack v1.
 */
export const ContextSkills = {
  /** Four-step playbook for markdown-rate spike diagnosis: seasonality → competitor pricing → stock aging → promo cannibalisation. M14 pilot (Scenario 1 of ADR-037). */
  DiagnoseMarkdownSpike: "diagnose_markdown_spike",
  /** Deterministic 6-step playbook for refund-eligibility decisioning: enrichment → window check (with VIP exception) → limited-edition fee + chargeback escalation → refund_amount compute → approve-with-confidence. Shipped reference implementation on the customer-service-agent. */
  EvaluateRefundEligibility: "evaluate_refund_eligibility",
} as const;
export type ContextSkillsKey = keyof typeof ContextSkills;
export type ContextSkillsValue = (typeof ContextSkills)[ContextSkillsKey];

/**
 * Canonical ontology entity names in the Konstera Standard Context Pack v1.
 */
export const ContextEntities = {
  /** On-hand + inbound - allocated inventory; the committable quantity. */
  AvailableToPromise: "available_to_promise",
  /** A product's brand of record — own-brand or licensed/third-party. */
  Brand: "brand",
  /** A taxonomic grouping of products (menswear → outerwear → jackets). */
  Category: "category",
  /** The sales channel for an order: web / mobile / store / marketplace / wholesale. */
  Channel: "channel",
  /** A card-issuer-initiated dispute against a settled transaction. */
  Chargeback: "chargeback",
  /** A product grouping curated by the merchandising team — e.g. 'Linen 2026'. */
  Collection: "collection",
  /** A person or organisation with a persistent identity in the tenant's commerce system. */
  Customer: "customer",
  /** The physical act of picking + packing + shipping an order_line. */
  Fulfilment: "fulfilment",
  /** A customer's purchase, composed of one or more order_line entities. */
  Order: "order",
  /** One SKU + quantity within an order; the finest refund + fulfilment granularity. */
  OrderLine: "order_line",
  /** A parent product grouping one-or-more SKU variants (size, colour). */
  Product: "product",
  /** Konstera's record of goods on order from a supplier. */
  PurchaseOrder: "purchase_order",
  /** The money motion back to the customer following an approved return. */
  Refund: "refund",
  /** A geographic region used for merchandising + reporting splits. */
  Region: "region",
  /** A customer-initiated reversal of a delivered order_line. */
  Return: "return",
  /** The merchandising season (SS26, AW25) a product collection belongs to. */
  Season: "season",
  /** An inbound shipment of purchased goods from a supplier. */
  Shipment: "shipment",
  /** Stock keeping unit — the finest sellable product variant. */
  Sku: "sku",
  /** Current on-hand inventory in units, by SKU × location. */
  StockOnHand: "stock_on_hand",
  /** A physical retail location. */
  Store: "store",
  /** A vendor the business places purchase orders against. */
  Supplier: "supplier",
  /** A customer-service inquiry recorded in the ticketing system. */
  Ticket: "ticket",
  /** A specific size/colour/material combination of a product; typically a 1:1 with SKU. */
  Variant: "variant",
  /** Named loyalty tier (silver / gold / platinum) attached to a customer. */
  VipTierLevel: "vip_tier_level",
} as const;
export type ContextEntitiesKey = keyof typeof ContextEntities;
export type ContextEntitiesValue = (typeof ContextEntities)[ContextEntitiesKey];
