# Sam Meat Intake Contract

## Status

Phase 11C contract build.

This is the first customer-facing meat-sales intake contract for Sam. It is not a customer-send, preorder, deposit, stock-allocation, or order-creation workflow yet.

## Role Split

| Role | Owns | Does not own |
| --- | --- | --- |
| Sam | Customer conversation in Chatwoot channels and structured meat-interest intake | Business strategy, pricing approval, deposit request authority, stock allocation |
| Ledger | Sales opportunity, pricing/margin review, owner queue, next action | Customer conversation |
| Backend | Lead/preorder state, validation, missing-field calculation, audit flags | Natural customer wording |
| Oom Sakkie/Gatekeeper | Owner visibility and approval gates | Direct customer sales conversation |

Sam stays one customer-facing agent. Internally, Sam routes into lanes such as `live_pig_sales`, `meat_preorder`, and later `assisted_slaughter`.

## Current Endpoint

Review-gated local contract endpoint:

```text
POST /api/oom-sakkie/sales-leads/sam-meat-intake
```

Current gate:

- local/review access only
- records an append-only sales lead only
- no customer send
- no Chatwoot/n8n/WhatsApp outbound call
- no quote/order/preorder/deposit
- no stock reservation or allocation write
- no financial action

This endpoint proves the backend payload contract before the live `1.0 Sam` and `1.2 Steward` workflow changes are made.

## Live n8n Gate Required

The current endpoint is not a production n8n-cloud ingest endpoint. Before Sam can save meat leads from live Chatwoot automation, add a separate remote-safe call path or Steward action with these controls:

- default-off environment flag
- bearer/API token, not local review access
- HTTPS for remote calls
- no hard-coded token in workflow JSON
- tests for disabled, missing-token, bad-token, and successful tracking-only cases
- tracking-only authority flags remain false for customer send, Chatwoot outbound, quote/order/preorder/deposit, stock/allocation, dispatch, and financial action

Until that gate exists, live Sam may continue the conversation but must not call this endpoint from n8n cloud.

Remote-safe route now available for private test after env setup:

```text
POST /api/oom-sakkie/channels/chatwoot/sam-meat-intake
```

Required env:

- `OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_ENABLED=1`
- `OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_TOKEN=<long random token, 32+ chars>`

Accepted auth:

- `Authorization: Bearer <token>`
- or `X-Amadeus-Sam-Intake-Key: <token>`

This route is default-off. It records only the same tracking lead contract and returns `remote_ingest` authority flags showing no customer send, Chatwoot call, n8n call, quote/order creation, stock change, or financial action.

## Append-Only Follow-Up Facts

The lead row stays append-only. Every accepted Sam meat-intake handoff also records a bounded `status_observed` event in `oom_sakkie_sales_lead_events` with `recorded_by = sam_meat_intake`.

The event notes contain a compact JSON fact snapshot for the same lead. This lets Sam record later conversation facts such as `collection`, `EFT`, or updated timing without mutating the original lead row.

Ledger/preorder-contract readback merges the original lead `interest_json` with the newest non-empty Sam fact snapshots before calculating missing money-path fields.

## Payload

```json
{
  "customer_name": "Jan",
  "conversation_id": "1234",
  "contact_id": "5678",
  "channel": "chatwoot_whatsapp",
  "whatsapp_window_state": "open",
  "product_type": "half_carcass",
  "cut_set": "Set A",
  "location": "Riversdale",
  "timing": "next available week",
  "delivery_or_collection": "collection",
  "price_per_kg": "",
  "deposit_rule": "",
  "payment_method": "EFT",
  "notes": "Wants price and timing",
  "status": "interested"
}
```

Allowed `product_type` values:

- `half_carcass`
- `full_carcass`
- `custom_cut`
- `assisted_slaughter`
- `unknown`

## Required Core Fields

Sam should collect these before the backend accepts a meat intake lead:

- `customer_name`
- `product_type`
- `location`

If one is missing, the backend returns `sam_meat_intake_missing_core_fields` and tells Sam the next question to ask.

## Required Before Money Path

These are not required to record the lead, but they are required before any preorder, deposit request, order, allocation, or customer-send automation:

- `cut_set`
- `timing`
- `delivery_or_collection`
- `price_per_kg`
- `deposit_rule`
- `payment_method`
- `owner_final_approval`

Sam may collect customer preferences, but owner approval is still required before the farm quotes or asks for deposit.

## Cut Menu Boundary

Sam may recognize a customer-selected cut set such as `Set A`, but Sam must not invent or describe the contents of Set A/Set B/Set C until an owner-approved cut menu source exists.

Until the cut menu source is added, if a customer asks what cuts are included, Sam should say the farm will confirm the exact cut set details before quoting.

## Response Shape

```json
{
  "success": true,
  "mode": "sam_meat_intake_tracking_only",
  "lead_id": "OSK-SALES-LEAD-...",
  "contract": {
    "lane": "meat_preorder",
    "missing_core_fields": [],
    "missing_before_money_path": ["price_per_kg", "deposit_rule", "owner_final_approval"],
    "sam_next_question": "I need to confirm the current price with the farm before quoting.",
    "authority": {
      "records_tracking_lead": true,
      "sends_customer_message": false,
      "calls_chatwoot": false,
      "calls_n8n": false,
      "creates_quote": false,
      "creates_order": false,
      "changes_stock": false,
      "writes_farm_data": false
    }
  }
}
```

## Next n8n Build

The next n8n slice should mirror the live-pig pattern:

1. `1.0 Sam` detects `meat_preorder` lane.
2. `1.0 Sam` extracts only bounded meat-intake fields.
3. `1.0 Sam` calls a Steward/backend action that records the tracking lead.
4. Sam asks only the next missing safe question.
5. Chatwoot custom attributes may keep lightweight routing hints, but backend lead/preorder state is truth.

Do not route this into live-pig `create_order_with_lines`. Meat preorders need their own reviewed contract because deposits, slaughter timing, cut sets, and final weights are different from live pig orders.

Detailed `1.0 Sam` handoff plan: `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/MEAT_INTAKE_HANDOFF_PLAN.md`.
