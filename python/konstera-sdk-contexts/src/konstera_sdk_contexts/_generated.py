# Generated from sdk/schemas/standard-context-pack-v1.json
# by sdk/scripts/generate_constants.py — do not edit by hand.
"""Standard Context Pack v1 — typed constants.

Mirror of Konstera.Sdk.Contexts (NuGet) and konstera-sdk-contexts (npm).
Agent authors import these names so typos fail at import time, not install.
"""
from typing import Final


class ContextTerms:
    """Canonical glossary names in the Konstera Standard Context Pack v1."""
    #: Average handle time per ticket, including hold + after-call work.
    AHT: Final[str] = "aht"
    #: Customer acquisition cost — blended cost to acquire a new paying customer.
    CAC: Final[str] = "cac"
    #: Boolean on a ticket indicating the customer has initiated a chargeback dispute with their card issuer. Blocks the refund path.
    CHARGEBACK_FILED: Final[str] = "chargeback_filed"
    #: Cost of goods sold — landed cost of the units that generated the revenue in the period.
    COGS: Final[str] = "cogs"
    #: Customer satisfaction score, 1-5, captured post-ticket.
    CSAT: Final[str] = "csat"
    #: Number of days of expected sell-through covered by current on-hand inventory.
    DAYS_COVER: Final[str] = "days_cover"
    #: Share of inquiries resolved without human agent contact. Measures self-service effectiveness.
    DEFLECTION_RATE: Final[str] = "deflection_rate"
    #: Contracted delivery service-level agreement — ship-to-doorstep in days by delivery_tier.
    DELIVERY_SLA: Final[str] = "delivery_sla"
    #: First-contact resolution rate — share of tickets resolved on the first customer interaction.
    FCR: Final[str] = "fcr"
    #: Current state of an order_line in the pick-pack-ship-deliver lifecycle: pending | picked | packed | shipped | out_for_delivery | delivered | failed.
    FULFILMENT_STATUS: Final[str] = "fulfilment_status"
    #: Gross margin return on inventory investment — gross margin ÷ average inventory cost.
    GMROI: Final[str] = "gmroi"
    #: (Revenue - COGS) ÷ Revenue.
    GROSS_MARGIN: Final[str] = "gross_margin"
    #: Percentage deducted from refund_amount when the returned SKU is limited_edition. Default 15%.
    LIMITED_EDITION_RESTOCKING_FEE: Final[str] = "limited_edition_restocking_fee"
    #: Customer lifetime value — predicted total revenue a customer generates over their relationship.
    LTV: Final[str] = "ltv"
    #: realised-markdown-dollars ÷ gross-sales-dollars. The canonical merchandising KPI for discount depth.
    MARKDOWN_RATE: Final[str] = "markdown_rate"
    #: Open-to-buy — planned receipts budget available for the balance of a period.
    OTB: Final[str] = "otb"
    #: Degree to which a promotional discount shifts sales within the catalog without generating incremental revenue.
    PROMO_CANNIBALISATION: Final[str] = "promo_cannibalisation"
    #: Number of days from delivery during which a return is accepted at full value under the standard policy.
    REFUND_WINDOW_DAYS: Final[str] = "refund_window_days"
    #: Enum reason the customer gave for the return: size | changed_mind | wrong_item | not_as_described | damaged | quality | late_delivery | other.
    RETURN_REASON_CODE: Final[str] = "return_reason_code"
    #: GAAP revenue excluding returns, net of discounts. The authoritative top-line figure.
    REVENUE: Final[str] = "revenue"
    #: Buffer inventory held to cover demand variability + supplier lead-time variance.
    SAFETY_STOCK: Final[str] = "safety_stock"
    #: Units sold ÷ units received, measured over a season or window.
    SELL_THROUGH: Final[str] = "sell_through"
    #: Loyalty tier assigned to a customer: silver | gold | platinum, with escalating policy exceptions.
    VIP_TIER: Final[str] = "vip_tier"
    #: Policy clause that extends refund_window_days for customers in a VIP tier and may waive restocking_fee.
    VIP_TIER_EXCEPTION: Final[str] = "vip_tier_exception"


class ContextSkills:
    """Canonical skill names in the Konstera Standard Context Pack v1."""
    #: Four-step playbook for markdown-rate spike diagnosis: seasonality → competitor pricing → stock aging → promo cannibalisation. M14 pilot (Scenario 1 of ADR-037).
    DIAGNOSE_MARKDOWN_SPIKE: Final[str] = "diagnose_markdown_spike"
    #: Deterministic 6-step playbook for refund-eligibility decisioning: enrichment → window check (with VIP exception) → limited-edition fee + chargeback escalation → refund_amount compute → approve-with-confidence. Shipped reference implementation on the customer-service-agent.
    EVALUATE_REFUND_ELIGIBILITY: Final[str] = "evaluate_refund_eligibility"


class ContextEntities:
    """Canonical ontology entity names in the Konstera Standard Context Pack v1."""
    #: On-hand + inbound - allocated inventory; the committable quantity.
    AVAILABLE_TO_PROMISE: Final[str] = "available_to_promise"
    #: A product's brand of record — own-brand or licensed/third-party.
    BRAND: Final[str] = "brand"
    #: A taxonomic grouping of products (menswear → outerwear → jackets).
    CATEGORY: Final[str] = "category"
    #: The sales channel for an order: web / mobile / store / marketplace / wholesale.
    CHANNEL: Final[str] = "channel"
    #: A card-issuer-initiated dispute against a settled transaction.
    CHARGEBACK: Final[str] = "chargeback"
    #: A product grouping curated by the merchandising team — e.g. 'Linen 2026'.
    COLLECTION: Final[str] = "collection"
    #: A person or organisation with a persistent identity in the tenant's commerce system.
    CUSTOMER: Final[str] = "customer"
    #: The physical act of picking + packing + shipping an order_line.
    FULFILMENT: Final[str] = "fulfilment"
    #: A customer's purchase, composed of one or more order_line entities.
    ORDER: Final[str] = "order"
    #: One SKU + quantity within an order; the finest refund + fulfilment granularity.
    ORDER_LINE: Final[str] = "order_line"
    #: A parent product grouping one-or-more SKU variants (size, colour).
    PRODUCT: Final[str] = "product"
    #: Konstera's record of goods on order from a supplier.
    PURCHASE_ORDER: Final[str] = "purchase_order"
    #: The money motion back to the customer following an approved return.
    REFUND: Final[str] = "refund"
    #: A geographic region used for merchandising + reporting splits.
    REGION: Final[str] = "region"
    #: A customer-initiated reversal of a delivered order_line.
    RETURN: Final[str] = "return"
    #: The merchandising season (SS26, AW25) a product collection belongs to.
    SEASON: Final[str] = "season"
    #: An inbound shipment of purchased goods from a supplier.
    SHIPMENT: Final[str] = "shipment"
    #: Stock keeping unit — the finest sellable product variant.
    SKU: Final[str] = "sku"
    #: Current on-hand inventory in units, by SKU × location.
    STOCK_ON_HAND: Final[str] = "stock_on_hand"
    #: A physical retail location.
    STORE: Final[str] = "store"
    #: A vendor the business places purchase orders against.
    SUPPLIER: Final[str] = "supplier"
    #: A customer-service inquiry recorded in the ticketing system.
    TICKET: Final[str] = "ticket"
    #: A specific size/colour/material combination of a product; typically a 1:1 with SKU.
    VARIANT: Final[str] = "variant"
    #: Named loyalty tier (silver / gold / platinum) attached to a customer.
    VIP_TIER_LEVEL: Final[str] = "vip_tier_level"
