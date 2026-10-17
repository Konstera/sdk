# Fixture file format — local dev without real vendor accounts

> **Who this is for.** Agent developers who need to run and test agents locally without pointing them at real Shopify / Zendesk / NetSuite dev stores. Also for LLM dev tools generating fixtures via the planned `fixture.generate` MCP tool.
>
> **What a fixture is.** A JSON file in `fixtures/<capability_name>/<scenario>.json` that the local kernel's stub-connector mode reads instead of calling a real vendor API. Each fixture pairs a `match` block (which input it responds to) with a `response` block (the canonical-shape payload returned).
>
> **Status.** The file format spec in this document is stable and will be honoured by the stub kernel. The *stub kernel itself* is planned — a `docker-compose.dev.yml` recipe that enables it ships in the next commit batch. Today, reference agents in `agents/*` use similar fixtures via their own `tests/` harnesses; migrating them to this spec is tracked separately.

---

## 1. File layout

```
fixtures/
├── customers.lookup_by_email/
│   ├── jane_platinum.json
│   ├── bob_silver.json
│   └── unknown.json
├── orders.lookup_by_id/
│   └── fulfilled_order.json
├── tickets.list_new/
│   ├── empty.json
│   └── three_tickets.json
└── refunds.create/
    └── success.json
```

Rules:
- Directory name is the capability name (dotted — matches `manifest.capabilities.needs[].name` exactly).
- File name within the directory is the scenario name — any `[a-z0-9_-]+.json`.
- The stub kernel loads every file at startup. Fixtures are hot-reloaded on change if `KONSTERA_STUB_WATCH=1`.

---

## 2. File schema

```jsonc
{
  "match":    { /* input matcher — see §3 */ },
  "response": { /* canonical-shape response — see §4 */ },

  // Optional metadata:
  "description": "Jane requests a refund; she's platinum tier.",
  "delayMs":     150,        // simulate latency; default 0
  "status":      "ok",       // ok | not_found | upstream_failure; default ok
  "errorDetail": { "code": "VENDOR_503", "message": "upstream unavailable" }
}
```

The `match` and `response` blocks are required. Metadata is optional.

---

## 3. The `match` block

Decides whether this fixture responds to a given capability call. First match in alphabetical file order wins.

### 3.1 Exact match

The common case — the fixture's `match` fields must equal the call's arguments.

```jsonc
// fixtures/customers.lookup_by_email/jane_platinum.json
{
  "match":    { "email": "jane@example.com" },
  "response": { "id": "cust_7823456", "email": "jane@example.com", "vip_tier": "platinum", /*...*/ }
}
```

A call `ctx.capability.call("customers.lookup_by_email", email="jane@example.com")` matches this fixture. A call with a different email does not.

### 3.2 Multiple-field match

All fields in `match` must equal the corresponding call arguments.

```jsonc
// fixtures/orders.lookup_by_id/order_in_window.json
{
  "match":    { "orderId": "ord_123", "includeItems": true },
  "response": { "orderId": "ord_123", "status": "fulfilled", "items": [/*...*/] }
}
```

### 3.3 Wildcard match

A `match` value of `"*"` matches any value for that field. Useful for fallback fixtures.

```jsonc
// fixtures/customers.lookup_by_email/unknown.json
{
  "match":    { "email": "*" },
  "response": null,              // returned as CapabilityError.NotFound
  "status":   "not_found"
}
```

Place these fixtures last alphabetically (e.g. prefix with `zz_`) so exact matches win first. The stub kernel loads them in filename order.

### 3.4 Pattern match (planned)

Regex / glob matching on fields is on the roadmap but not shipped. For v1, use exact match + a wildcard fallback.

---

## 4. The `response` block

Must match the capability's **canonical response schema** — the shape declared in the capability catalogue. Not the vendor's native shape.

### 4.1 Example — `orders.lookup_by_id`

Canonical schema (per the MVP catalogue in [llms-full.txt §4](../llms-full.txt)):
```
{ orderId, status, total, currency, items[], placedAt }
```

Fixture:
```jsonc
{
  "match": { "orderId": "ord_123" },
  "response": {
    "orderId":   "ord_123",
    "status":    "fulfilled",
    "total":     149.95,
    "currency":  "USD",
    "items": [
      { "sku": "SKU-A", "quantity": 1, "price": 149.95 }
    ],
    "placedAt":  "2026-10-14T14:22:00Z"
  }
}
```

### 4.2 Example — `tickets.list_new`

Canonical schema returns an **array**:
```
[{ ticketId, threadId, subject, body, from, to, receivedAt }]
```

Fixture:
```jsonc
{
  "match": { "sinceIso": "*" },
  "response": [
    {
      "ticketId":   "tkt_001",
      "threadId":   "thr_001",
      "subject":    "Where's my order #20385?",
      "body":       "It's been 10 days, please help",
      "from":       "jane@example.com",
      "to":         "support@fragranceshop.example",
      "receivedAt": "2026-10-17T09:14:00Z"
    }
  ]
}
```

### 4.3 Example — `refunds.create`

Canonical schema:
```
{ refundId, status, amount, currency }
```

Fixture:
```jsonc
{
  "match": { "orderId": "ord_123" },
  "response": {
    "refundId":  "rfnd_7f3a9c",
    "status":    "approved",
    "amount":    149.95,
    "currency":  "USD"
  }
}
```

### 4.4 The `_source` field (for vendor-specific tests)

If an agent reads from `response["_source"]` (per the escape documented in [capabilities-and-ontology.md §7](capabilities-and-ontology.md#7-handling-vendor-specific-attributes--the-_source-escape)), include a `_source` block in the fixture so the test exercises that path:

```jsonc
{
  "match": { "email": "jane@example.com" },
  "response": {
    "id":    "cust_7823456",
    "email": "jane@example.com",
    "vip_tier": "platinum",
    "_source": {
      "connector": "shopify",
      "native_id": "7823456789012",
      "tags":      ["tier:platinum", "newsletter"]
    }
  }
}
```

---

## 5. Simulating failures

The `status` field drives what the stub kernel returns:

| `status`           | Agent sees                                                                       |
| ------------------ | -------------------------------------------------------------------------------- |
| `ok` (default)     | The `response` payload                                                           |
| `not_found`        | `CapabilityError.NotFound` — `response` may be `null`                            |
| `upstream_failure` | `CapabilityError.UpstreamFailure` with `errorDetail`; retries do not apply in stub mode |
| `shape_invalid`    | `CapabilityError.ResponseShapeInvalid` — useful for testing shape-mismatch handling |

Example — testing an agent's handling of a vendor outage:

```jsonc
// fixtures/orders.lookup_by_id/vendor_down.json
{
  "match":       { "orderId": "ord_outage" },
  "status":      "upstream_failure",
  "errorDetail": { "code": "VENDOR_503", "message": "shopify.myshopify.com returned 503" }
}
```

The scenario in `manifest.eval.scenarios[]` can then assert the agent escalates rather than silently failing.

---

## 6. Latency simulation

`delayMs` makes the stub kernel wait before responding. Useful for testing timeout behaviour or UI loading states (if the agent produces streamed output).

```jsonc
{
  "match":   { "query": "*" },
  "delayMs": 2000,
  "response": [/* ...large result set... */]
}
```

Default is 0. Do not use this for load testing — the stub kernel is not a load generator.

---

## 7. Capturing fixtures from a live tenant (planned)

Rather than hand-writing fixtures, developers will be able to capture real responses from a dev tenant via `konstera-agent record`:

```bash
# Planned
konstera-agent record \
    --tenant dev \
    --capability customers.lookup_by_email \
    --input '{"email": "jane@example.com"}' \
    --save-as fixtures/customers.lookup_by_email/jane_platinum.json
```

The capture tool will:
- Call the live capability via the dev tenant's bindings.
- Apply configured PII masks (email domains, phone number middle digits, etc.) so captures don't carry real customer data into the repo.
- Write a fixture file in this exact format, with a `match` block derived from `--input`.

Until this tool ships, hand-write fixtures from the canonical response schema. The schema for every MVP capability is in [llms-full.txt §4](../llms-full.txt).

---

## 8. Validating fixtures against the catalogue

The stub kernel validates every fixture's `response` block against the capability's canonical schema on startup. A fixture with a missing required field or a wrong type refuses to load and the kernel logs:

```
[stub] fixture fixtures/orders.lookup_by_id/bad.json rejected:
  response.currency: required field missing
```

This is deliberately strict — a bad fixture that silently returns the wrong shape would produce passing agent tests that fail in production. If you see this error, align the fixture to the schema.

The planned `fixture.generate` MCP tool will produce schema-conformant fixtures by construction.

---

## 9. Mixing stub and live modes

A single agent run can mix stub and live modes per-capability. Useful during development:

```bash
# Stub everything except tickets.* — point those at a real Zendesk sandbox
KONSTERA_STUB_EXCEPT="tickets.*" docker compose -f docker-compose.dev.yml up -d
```

Capabilities named in `KONSTERA_STUB_EXCEPT` resolve to real connections configured in the dev tenant; everything else reads fixtures.

Rules:
- Live capabilities must have real bindings in the local tenant.
- Mixing is for dev convenience; production never runs in stub mode (the kernel refuses `KONSTERA_STUB_MODE=1` in a non-local tenant).

---

## 10. Common pitfalls

| Pitfall | Fix |
| ------- | --- |
| Fixture refuses to load — "response.X: required field missing" | Align the fixture to the capability's canonical schema. See [llms-full.txt §4](../llms-full.txt) or run `catalogue.get_capability` MCP tool. |
| Fixture isn't being matched | Check `match` block carefully. All fields must equal exactly (or use `"*"` wildcard). Check alphabetical file order — a wildcard-fallback fixture named `aaa_fallback.json` will shadow more specific ones. |
| Agent reads `customer["tags"]` and the test passes with a fixture but fails in production | The agent is reading a vendor-specific field as if canonical. The fixture reinforced the bug. Move the read to `customer["_source"]["tags"]` with a comment noting the vendor tie. |
| Fixture is huge | If you're hand-copying a vendor response verbatim, you're probably over-fixturing. Keep only the fields the agent actually reads. |
| Test passes in stub mode, fails in live mode | A real response has extra fields or edge cases your fixture doesn't. Capture a real one via `konstera-agent record` (when shipped) or extend the fixture by hand. |

---

## 11. Related reading

- **[capabilities-and-ontology.md](capabilities-and-ontology.md)** — the pattern the fixtures support
- **[end-to-end-journey.md §2.5](end-to-end-journey.md)** — where fixtures sit in the lifecycle
- **[AGENTS.md](AGENTS.md)** — summary of the fixture pattern for LLM dev tools
- **[llms-full.txt §4](../llms-full.txt)** — canonical schemas for every MVP capability
- `platform/docs/adr/013-agent-capabilities.md` — the technical ADR behind the canonical-shape pattern
