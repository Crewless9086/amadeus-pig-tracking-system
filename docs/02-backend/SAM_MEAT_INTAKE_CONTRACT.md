# Sam Meat Intake Contract

## Status

Phase 11C backend-native Sam Meat cutover.

This is the first backend-owned customer-facing meat-sales intake runtime for Sam. n8n remains fallback while the backend Chatwoot webhook is smoke-tested, but the target architecture is Chatwoot -> Flask backend -> Sam Meat runtime -> backend audit events / controlled Chatwoot reply.

## Role Split

| Role | Owns | Does not own |
| --- | --- | --- |
| Sam | Customer conversation in Chatwoot channels and structured meat-interest intake | Business strategy, pricing approval, deposit request authority, stock allocation |
| Ledger | Sales opportunity, pricing/margin review, owner queue, next action | Customer conversation |
| Backend | Chatwoot inbound webhook, Sam Meat runtime, lead/preorder state, validation, missing-field calculation, audit flags, controlled Chatwoot sends | Autonomous pricing, reservation, stock changes, public posting |
| Oom Sakkie/Gatekeeper | Owner visibility and approval gates | Direct customer sales conversation |

Sam stays one customer-facing agent. Internally, Sam routes into lanes such as `live_pig_sales`, `meat_preorder`, and later `assisted_slaughter`.

## Current Backend-Native Target

Inbound Chatwoot webhook:

```text
POST /api/sales/channels/chatwoot/sam-meat/inbound
```

Required env:

- `SAM_MEAT_BACKEND_WEBHOOK_ENABLED=1`
- `SAM_MEAT_BACKEND_WEBHOOK_TOKEN=<long random token, 32+ chars>`
- `SAM_MEAT_BACKEND_AUTOREPLY_ENABLED=1` only when backend replies are allowed
- `CHATWOOT_BASE_URL=https://app.chatwoot.com`
- `CHATWOOT_ACCOUNT_ID=147387`
- `CHATWOOT_API_ACCESS_TOKEN=<Chatwoot token>`
- `SAM_MEAT_BACKEND_LLM_ENABLED=1` only if LLM extraction is allowed
- `SAM_MEAT_BACKEND_LLM_MODEL=<model>` when LLM extraction is enabled
- `OPENAI_API_KEY=<optional for LLM extraction; deterministic fallback remains required>`

Accepted auth:

- `Authorization: Bearer <token>`
- or `X-Amadeus-Sam-Meat-Webhook-Key: <token>`

Runtime rules:

- inbound webhook ignores outbound/system/non-message events
- inbound webhook records only append-only lead/fact events
- Sam Meat may ask clarifying intake questions when facts are missing
- Sam Meat must not quote price, promise slaughter timing, request deposit, create orders, reserve stock, or change stock from normal inbound chat
- any outbound Chatwoot send requires the backend autoreply env gate and an open customer-service window
- owner price/timing/deposit approval, exact follow-up approval, customer yes, and Draft order creation remain separate Farm App gates

Safe pork cut-menu replies are allowed from the documented pork model only:

- Set A: Family Freezer Pack: pork chops, leg portions or roasts, shoulder roasts, belly strips, ribs, mince or stew meat, and bones for soup or stock.
- Set B: Braai Pack: chops, rashers or belly strips, ribs, shoulder steaks, sosatie or stew cubes, and mince or sausage meat option.
- Set C: Lean Pack: lean chops, leg steaks, lean shoulder cuts, mince, stew cubes, and fewer fatty belly cuts.
- Set D: Budget Bulk Pack: larger roasting cuts, mince, stew meat, soup bones, shoulder, mixed chops, and less detailed trimming.

These descriptions do not grant pricing, timing, deposit, booking, order, or stock authority.

## Legacy/Compatibility Endpoint

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

## Ledger Owner Money-Path Approval

Ledger owner review is an append-only event, not a mutation of the original lead row.

Review-gated endpoint:

```text
POST /api/oom-sakkie/sales-leads/<lead_id>/owner-money-path-approval
```

Required owner fields:

- `price_per_kg`
- `available_week`
- `estimated_weight_or_size`
- `deposit_rule` or `deposit_amount_or_rule`
- `payment_method`
- `delivery_or_collection`
- `owner_final_approval`

This records an `owner_money_path_approved` event only. It does not send a customer message, call Chatwoot/n8n, create a quote/order/preorder, reserve stock, update allocation, or perform any financial action.

After this event exists, `GET /api/oom-sakkie/sales-leads/<lead_id>/preorder-contract` merges Sam facts plus the owner approval event and returns `contract_status = owner_money_path_ready` when no money-path fields are missing.

## Customer Follow-Up Draft

Review-gated endpoint:

```text
GET /api/oom-sakkie/sales-leads/<lead_id>/customer-followup-draft
```

This endpoint only works when the preorder contract is `owner_money_path_ready`.

It returns a deterministic owner-review customer draft for Sam/Chatwoot wording. It does not store a send request, send a message, call Chatwoot/n8n, create a quote/order/preorder, reserve stock, update allocation, or perform a financial action.

The draft asks the buyer whether they want the approved details sent through for final booking review. Customer acceptance must still go through a separate owner-reviewed booking/order/deposit rail before any real order, deposit request, stock reservation, or formal quote workflow exists.

## Sam/Chatwoot Send Handoff Design

Review-gated endpoint:

```text
GET /api/oom-sakkie/sales-leads/<lead_id>/customer-followup-send-design
```

This endpoint turns the approved customer follow-up draft into a send handoff design packet only. It defines the future target transport, proposed payload, runtime gates, owner checks, and blocked actions.

It does not send the draft, call Chatwoot, call n8n, create a send request, create a quote/order/preorder, reserve stock, update allocation, or perform a financial action.

The next unlock after this design must be a separate owner-approved send consumer with explicit authentication, exact-message verification, WhatsApp window/channel checks, and append-only audit events before and after any attempted customer send.

## Token-Gated Customer Follow-Up Send

Owner approval endpoint:

```text
POST /api/oom-sakkie/sales-leads/<lead_id>/customer-followup-send-approval
```

This records `owner_customer_followup_send_approved` for the exact message returned by the follow-up draft/design. If the message text differs, the backend rejects it.

Remote send consumer:

```text
POST /api/oom-sakkie/channels/chatwoot/sales-leads/<lead_id>/customer-followup-send
```

Required env:

- `OOM_SAKKIE_MEAT_FOLLOWUP_SEND_ENABLED=1`
- `OOM_SAKKIE_MEAT_FOLLOWUP_SEND_TOKEN=<long random token, 32+ chars>`
- `CHATWOOT_BASE_URL=https://app.chatwoot.com`
- `CHATWOOT_ACCOUNT_ID=147387`
- `CHATWOOT_API_ACCESS_TOKEN=<Chatwoot token>`

Accepted auth:

- `Authorization: Bearer <token>`
- or `X-Amadeus-Meat-Followup-Send-Key: <token>`

The send consumer verifies all of these before calling Chatwoot:

- remote send env is enabled
- remote token matches
- message text exactly matches the generated approved draft
- latest owner send approval event has the same message hash
- no previous `customer_followup_sent` event exists for that message hash
- lead has an open WhatsApp window
- lead has a Chatwoot conversation ID

It records `customer_followup_send_attempted` and then `customer_followup_sent` or `customer_followup_send_failed` audit events. It still does not create a quote, order, preorder, deposit request, stock reservation, or allocation.

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

Sam may recognize and describe the approved cut sets from `docs/08-business-modules/PORK_SALES_MODEL.md` rows 246-303.

Sam must not invent extra cuts or treat cut-set selection as price, availability, deposit, or booking approval. Those remain owner/Ledger gated.

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
