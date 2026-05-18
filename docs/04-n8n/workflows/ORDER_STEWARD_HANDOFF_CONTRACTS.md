# Order Steward Handoff Contracts

Phase 7.1B defines the intended `1.0 -> 1.2` handoff shape before workflow cleanup.

Status: planning and contract verification only. Do not remove fallback reads or duplicate fields until the relevant contract is tested and live-verified.

## Boundary

- `1.0 - Sam Sales Agent` decides the customer-facing route and sends one action request.
- `1.2 - Amadeus Order Steward` normalizes the action request and calls backend order/document endpoints.
- Backend APIs remain the source of truth for order state, line state, reservation, quote, and document status.
- Chatwoot attributes are only lightweight routing state, not order history.

## Shared Fields

These fields may be accepted by `1.2` and normalized before routing:

| Field | Purpose |
| --- | --- |
| `action` | Required discriminator for the steward switch. |
| `order_id` | Existing order identifier for read/update/lifecycle/document actions. |
| `changed_by` | Operator/source label, usually `Sam` or a phase-specific Sam label. |
| `conversation_id` | Needed for active lookup and document send. |
| `account_id` | Needed for document send; defaults to Chatwoot account `147387` where appropriate. |
| `contact_id` | Context only; useful when linking intake/customer records. |
| `customer_name`, `customer_phone`, `customer_channel`, `customer_language` | Draft creation and customer context. |
| `requested_category`, `requested_weight_range`, `requested_sex`, `requested_quantity` | Draft header or update facts. |
| `requested_items[]` | Line sync facts. Each item should include `request_item_key`, `category`, `weight_range`, `sex`, `quantity`, `intent_type`, `status`, and optional `notes`. |
| `collection_location`, `payment_method`, `notes` | Draft/update facts and quote readiness facts. |
| `send_quote_if_ready` | Create path flag used by `1.2` to decide whether to run the separate post-create send flow. |
| `created_from_intake`, `intake_id` | Metadata used by `1.0` to link the created order back to intake state. |

## Action Contracts

| Action | Required input | Optional input | Expected result |
| --- | --- | --- | --- |
| `create_order_with_lines` | customer fields, requested header fields, `requested_items[]`, `collection_location`, `payment_method`, `conversation_id`, `changed_by` | `send_quote_if_ready`, `created_from_intake`, `intake_id`, `account_id`, `contact_id` | `success`, `order_id`, `order_status`, `create_success`, `sync_success`, fulfillment fields, `auto_quote`, optional `quote_send`, intake metadata echo |
| `update_order` | `order_id`, `changed_by`, at least one updatable order field | `payment_method`, `collection_location`, requested fields, `notes` | `success`, `order_id`, `updated_fields`, `auto_quote` |
| `sync_order_lines_from_request` | `order_id`, `changed_by`, `requested_items[]` | none for normal customer flow | `success`, `order_id`, fulfillment fields, `results`, `incomplete_items`, `auto_quote` |
| `cancel_order` | `order_id`, `changed_by` | `reason` | `success`, `order_id`, `order_status = Cancelled`, `payment_status = Cancelled`, `cancelled_line_count` |
| `send_for_approval` | `order_id`, `changed_by` | none | `success`, `order_id`, `order_status = Pending_Approval`, `approval_status = Pending`, or backend guard error |
| `generate_quote` | `order_id`, `changed_by` | `conversation_id` for context | `success`, `order_id`, `document_id`, `document_ref`, `document_status`; does not send |
| `send_latest_quote` | `order_id`, `conversation_id`, `changed_by` | `account_id` | `success`, `order_id`, `document_id`, `document_ref`, `document_status`, `delivery_webhook_sent` |
| `get_order_context` | `order_id` | `changed_by` | `success`, `order_id`, `existing_order_context` with slim order and line summary |
| `get_active_customer_order_context` | at least one of `order_id`, `conversation_id`, `customer_phone` | `changed_by` | `success`, `lookup_status`, `match_count`, `active_order_context`, `active_order_matches` |

## Cleanup Rules

- Do not let `1.0` pass raw Sam prompt context into `1.2`.
- Do not let `1.2` return raw backend payloads when a compact action result is enough.
- Do not remove a fallback read until the target node has one agreed source in this contract.
- Do not give Sam direct order sheet access. Add read-only backend/steward actions for current or historical order context.
- Keep live workflow tests small and slow enough to avoid Sheets quota pressure.

## Phase 7.1C Slim Result Shapes

These are the target consumer-facing shapes for Sam replies and Chatwoot updates. They define what downstream nodes should rely on before payload cleanup begins.

### `sam_order_state_slim`

Owned by `1.0 Code - Slim Sales Agent User Context`.

Purpose: give Sam a compact current-turn order state summary without raw workflow internals.

Allowed fields:

- customer basics: `customer_name`, `customer_language`
- active order link: `existing_order_id`, `existing_order_status`
- routing state: `conversation_mode`, `pending_action`
- operational cache: `payment_method`
- requested facts: `requested_quantity`, `requested_category`, `requested_weight_range`, `requested_sex`, `timing_preference`, `collection_location`
- intent flags only when needed for the current reply

Should not include:

- raw `intake_payload`
- raw `intake_raw_response`
- full `requested_items[]` when a compact summary is enough
- raw Chatwoot payloads
- full backend order/detail payloads

### `sam_steward_result_compact`

Owned by `1.0 Code - Slim Sales Agent User Context`.

Purpose: give Sam a compact, backend-confirmed summary of the latest steward/backend result.

Allowed fields:

- active lookup: `active_order_lookup_status`, `active_order_match_count`, `active_order_lookup_message`
- active order summary: `active_order_summary`, `active_order_line_groups`, `active_order_matches`
- fulfillment: partial/complete/no-match wording fields derived from steward results
- quote readiness: `auto_quote`, `generated_document`, `generated_document_url_available`
- quote sending: `quote_send`, `quote_send_document_ref`, `quote_send_document_status`, `delivery_webhook_sent`

Should not include:

- raw `results[]` if a compact fulfillment summary exists
- raw document payloads
- raw Google Drive internals beyond a boolean that a URL is available
- internal node debug fields

### `existing_order_context`

Owned by `1.2 get_order_context` and `1.0` context attach nodes.

Purpose: provide a slim current-order read model for routing and Sam replies.

Shape:

```json
{
  "order": {
    "order_id": "",
    "order_status": "",
    "approval_status": "",
    "payment_status": "",
    "customer_name": "",
    "requested_category": "",
    "requested_weight_range": "",
    "requested_sex": "",
    "requested_quantity": "",
    "collection_date": "",
    "collection_location": "",
    "line_count": 0,
    "active_line_count": 0,
    "line_count_includes_cancelled": true,
    "payment_method": "",
    "notes": ""
  },
  "lines": [
    {
      "order_line_id": "",
      "pig_id": "",
      "sale_category": "",
      "weight_band": "",
      "sex": "",
      "line_status": ""
    }
  ]
}
```

### Chatwoot Custom Attributes

Chatwoot should consume only stable lightweight fields:

- `order_id`
- `order_status`
- `conversation_mode`
- `pending_action`
- `payment_method`

Do not write full context, quote details, requested items, or old order history into Chatwoot custom attributes.

## Phase 7.1D Chatwoot `order_id` Lifecycle Policy

Purpose: keep Chatwoot useful for the current customer conversation without turning it into order history.

Decision:

- Chatwoot may link one current order at a time through `custom_attributes.order_id`.
- Chatwoot `order_id` is a routing pointer, not the source of truth and not a full customer order history.
- Backend order APIs and `1.2` read-only actions remain the source of truth for active, cancelled, completed, and old orders.
- Do not clear or replace `order_id` from Chatwoot unless the triggering action is backend-confirmed or the customer clearly starts a new order.

Lifecycle rules:

| Scenario | Chatwoot `order_id` | Chatwoot `order_status` | Required behavior |
| --- | --- | --- | --- |
| Draft / Pending Approval / Approved | Keep current order ID | Mirror backend-confirmed status | Treat as the active customer order. Updates, cancellation, approval, quote-send, and review actions may use the linked ID. |
| Cancelled by customer/backend | Keep the cancelled order ID for immediate follow-up | `Cancelled` | Clear `pending_action`. Sam may explain the cancellation using backend/steward context. A later new-order intent may replace the link with the new draft order ID after backend create succeeds. |
| Completed | Keep the completed order ID until a new-order intent creates a new draft | `Completed` | Sam must not update/cancel the completed order. Old-order questions should use read-only order/detail or future history lookup. New buying intent should start a new draft and then replace Chatwoot `order_id` after create succeeds. |
| No linked order | Blank | Blank or absent | Use active-order lookup only for review/cancel/document-style wording. Normal buying intent should create a new draft only after intake/draft rules are satisfied. |
| Multiple active matches | Do not overwrite with a guessed order ID | Preserve existing lightweight fields | Sam asks one disambiguation question. Workflow must not choose an order from multiple matches without customer confirmation. |
| Old order follow-up | Keep current link unless the customer gives a specific old order reference | Preserve current link | Use a future read-only history/detail action for old orders. Do not write old order history or old document details into Chatwoot attributes. |

Replacement rule:

- A new backend-confirmed draft can replace an old `order_id` when the customer's latest message is a clear new-order intent and the create action succeeds.
- Do not replace an active Draft / Pending Approval / Approved order just because a customer asks a general stock question.
- If the customer has an active order and appears to be starting a second order, Sam should first clarify whether to update the current order or start a new one. The current operating assumption remains one active order per customer conversation.

Pending action rule:

- `pending_action` is only a short-lived next-turn instruction such as `cancel_order` or `send_quote`.
- Clear `pending_action` after backend-confirmed completion of that pending action, after customer rejection, or when the workflow deliberately returns to normal AUTO conversation.
- Never keep `pending_action` for cancelled or completed orders unless a deliberate read-only follow-up flow is added later.

Payment method rule:

- Keep `payment_method` in Chatwoot for now as an operational cache for pending actions and escalation recovery.
- Backend order detail remains the source of truth. A later cleanup may remove the cache only after active-order context reliably provides payment method on every needed path.

## Phase 7.1E Chatwoot Write Pattern

Decision:

- Keep the existing separate Chatwoot HTTP write nodes for now.
- Standardize them around the same lightweight field order:
  1. `order_id`
  2. `order_status`
  3. `conversation_mode`
  4. `pending_action`
  5. `payment_method`
- Extra escalation fields are allowed only on the human-mode write node after the five standard fields.
- Do not add quote/document details, requested items, old order history, or raw backend context to Chatwoot custom attributes.

Current approved writer nodes in `1.0`:

- `HTTP - Set Conversation Human Mode`
- `HTTP - Set Conversation Order Context`
- `HTTP - Set Conversation Context After Update`
- `HTTP - Clear Pending After Cancel`
- `HTTP - Set Pending Cancel Action`
- `HTTP - Clear Pending Action`
- `HTTP - Set Chatwoot After Send Approval`
- `HTTP - Clear Pending After Send Quote`
- `HTTP - Set Pending Send Quote After Sync`
- `HTTP - Set Pending Send Quote After Generate`

Implementation note:

- `HTTP - Set Conversation Human Mode` was standardized to the same n8n expression style as the other Chatwoot write nodes.
- The write nodes remain separate because changing node topology would increase import risk during cleanup. A future helper-style pattern can be considered only after one live import proves this smaller standardization.

## Phase 7.1F Workflow Export Validation

Decision:

- The current `1.0` and `1.2` exports are ready for a controlled n8n import/live smoke pass from a validation standpoint.
- No further workflow JSON cleanup is required before import unless a new issue is found during import or smoke testing.

Local validation now checks:

- both workflow exports parse as JSON
- both exports have expected top-level `nodes` and `connections`
- every connection source and target references an existing node
- every n8n Code-node `jsCode` block passes JavaScript syntax checking with Node
- the steward action contract remains intact
- the slim Sam/steward context contracts remain intact
- every approved Chatwoot custom-attribute write keeps the lightweight fields in standard order

Live smoke recommendation:

- Import `1.0 - Sam Sales Agent Chatwoot` first because 7.1E changed that export.
- Re-import `1.2 - Order Steward` only if the n8n instance is not already aligned with the repo export.
- Use one controlled customer conversation smoke after import:
  - confirm existing linked order context still reads
  - confirm pending quote/cancel custom attributes are preserved
  - confirm human escalation still preserves order context
- Keep the live smoke narrow to avoid unnecessary Google Sheets quota pressure.

## Phase 7.1G n8n Import Checkpoint

Completed on 2026-05-18:

- Uploaded `1.0 - SAM - Sales Agent - Chatwoot` (`V73HaIqVpzv44SFc`) through the n8n public API.
- The workflow remained active after upload.
- Readback from n8n confirmed:
  - workflow ID `V73HaIqVpzv44SFc`
  - active `true`
  - 112 nodes
  - `HTTP - Set Conversation Human Mode` body matches the local 7.1E standardized expression
- Checked live `1.2 - Amadeus Order Steward` (`YDRs6fwde7MzPYn7`) without re-importing:
  - active `true`
  - 55 nodes
  - node count, connection count, and node names match the repo export

Smoke decision:

- Do not force a customer conversation through human escalation just to test the one standardized Chatwoot write. That would create unnecessary Chatwoot/Telegram side effects.
- Treat this checkpoint as an API import/readback smoke for the 7.1E workflow JSON change.
- If the next normal live conversation touches create/update, quote pending, cancel pending, or escalation, verify the Chatwoot attributes from that execution and record the result.

## Validation

Before importing changed workflows:

1. Parse `1.0` and `1.2` workflow JSON.
2. Compile all Code-node JavaScript.
3. Confirm `1.2` switch still supports every action in this contract.
4. Confirm `1.2 Code - Normalize Order Payload` still normalizes the shared fields.
5. Confirm `1.0 Code - Slim Sales Agent User Context` still emits `sam_order_state_slim` and `sam_steward_result_compact`.
6. Confirm active-order context formatter nodes still preserve the slim context fields.
7. Confirm every `1.0` Chatwoot custom attribute write preserves the approved lightweight fields and the standard field order.
8. Run the local backend suite.
9. Run one controlled production checkpoint only after deployment.
