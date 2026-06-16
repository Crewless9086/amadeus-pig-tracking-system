# Sam Meat Intake Handoff Plan

## Status

Phase 11C n8n handoff wired in the repo export. It remains default-off and must not be activated in live customer automation until backend env vars, n8n variables, and owner live-smoke approval are complete.

## Goal

Sam should collect meat preorder interest from Chatwoot channels and save the structured facts to the backend lead rail. Charl should not have to manually gather the first-pass intake details from WhatsApp, Messenger, Instagram, Facebook, or email.

This handoff is tracking only. It does not create an order, reserve stock, request a deposit, quote a price, send a payment instruction, or promise availability.

## Role Boundary

| Part | Responsibility |
| --- | --- |
| Sam in `1.0` | Detect meat preorder intent, ask one safe missing-field question, keep the customer conversation natural. |
| Backend contract | Validate the bounded intake payload, record append-only lead evidence, calculate missing fields and next safe question. |
| Ledger | Review owner action, price/kg, available week, deposit rule, margin/risk, and final approval. |
| Steward `1.2` | Later action owner for approved backend calls. It must not route meat preorder into live-pig `create_order_with_lines`. |

## Detection

Sam may enter `meat_preorder` when the customer asks about:

- half carcass
- full carcass
- pork meat packs or cut sets
- slaughter/cutting timing
- meat price/kg
- deposit for meat preorder

Sam should stay in `live_pig_sales` when the customer wants live pigs, piglets, weaners, growers, finishers, or breeding animals.

If both live pig and meat interest appear in the same conversation, Sam should ask one clarifying question before calling the meat intake handoff.

## Bounded Payload

The planned n8n payload must match `docs/02-backend/SAM_MEAT_INTAKE_CONTRACT.md`:

```json
{
  "customer_name": "",
  "conversation_id": "",
  "contact_id": "",
  "channel": "chatwoot_whatsapp",
  "whatsapp_window_state": "open",
  "product_type": "half_carcass",
  "cut_set": "Set A",
  "location": "Riversdale",
  "timing": "",
  "delivery_or_collection": "",
  "price_per_kg": "",
  "deposit_rule": "",
  "payment_method": "",
  "notes": "",
  "status": "interested"
}
```

Sam may only pass customer-provided or owner-confirmed facts. Empty strings are better than guessed values.

## Safe Question Order

Before saving a lead, Sam needs:

1. customer name
2. product type
3. customer location

After the lead exists, Sam can keep collecting preferences:

1. cut set
2. timing
3. delivery or collection preference
4. payment preference

Sam must not invent or confirm:

- price per kg
- available week
- deposit rule or amount
- final estimated carcass weight
- confirmed allocation
- final owner approval

## Chatwoot State

Chatwoot custom attributes may store only lightweight routing hints:

- `conversation_mode`
- `sales_lane = meat_preorder`
- `lead_id` after backend success
- `pending_action = owner_followup_needed` when the backend says money-path fields are missing

Do not wipe existing order context fields when updating these attributes. Preserve `order_id`, `order_status`, `conversation_mode`, `pending_action`, and `payment_method` unless a backend result explicitly changes them.

## Backend Call Path

Current local proof endpoint:

```text
POST /api/oom-sakkie/sales-leads/sam-meat-intake
```

Current state:

- review/local gated
- not callable from n8n cloud as a production endpoint
- append-only lead tracking only

Remote-safe private-test endpoint:

```text
POST /api/oom-sakkie/channels/chatwoot/sam-meat-intake
```

Required before n8n can call it:

- n8n variable `SAM_MEAT_INTAKE_HANDOFF_ENABLED` set truthy
- n8n variable `SAM_MEAT_INTAKE_REMOTE_TOKEN` set to the same token as the backend env
- optional n8n variable `SAM_MEAT_INTAKE_BASE_URL` if not using the default Render backend URL
- `OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_ENABLED=1`
- `OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_TOKEN` configured as a long random token of at least 32 characters
- token supplied through `Authorization: Bearer <token>` or `X-Amadeus-Sam-Intake-Key`
- token stored in n8n credentials or variables, not workflow JSON
- HTTPS for remote calls
- keep all authority flags false for customer send, quote/order/preorder/deposit, stock/allocation, dispatch, and financial action
- add tests for disabled, missing-token, bad-token, and successful tracking-only cases

Workflow nodes now present in `workflow.json`:

1. `Code - Build Sam Meat Intake Payload`
2. `IF - Sam Meat Intake Ready`
3. `HTTP - Sam Meat Intake Lead`
4. `Code - Attach Sam Meat Intake Result`

The branch sits after `Code - Attach Intake Result` and returns to the normal Sam classifier/context path through `Code - Attach Sam Meat Intake Result`.

## Acceptance

This handoff is ready to implement in workflow JSON only when:

- `1.0` detects `meat_preorder` separately from live pig sales
- payload fields match the backend contract
- missing fields produce one safe customer question
- Chatwoot attributes are preserved, not replaced wholesale
- the backend route is token-gated and default-off for remote use
- no live-pig order action is called for meat preorder
- owner approval remains required before price, timing, deposit, allocation, or preorder/order creation
