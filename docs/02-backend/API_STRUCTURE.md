# API Structure

## Purpose

Documents the current Flask order API used by the web app and n8n workflows.

All order API routes are registered under `/api`.

## Route Summary

| Method | Path | Current purpose | Main caller |
| --- | --- | --- | --- |
| `GET` | `/api/orders` | List orders from `ORDER_OVERVIEW`. | Web app, future review tooling. |
| `GET` | `/api/order-intake/context` | Read one active persistent intake state by Chatwoot `conversation_id`. | Future `1.0` shadow mode. |
| `POST` | `/api/order-intake/update` | Validate and merge an intake patch plus item patches into backend-owned intake sheets. | Future `1.0` shadow mode. |
| `POST` | `/api/order-intake/<conversation_id>/reset` | Close an active intake row without deleting history. | Admin/debug tooling, future `1.2`. |
| `GET` | `/api/orders/active-customer-context` | Safe active customer order lookup by `order_id`, `conversation_id`, or `customer_phone`. Returns one filtered context, a short multiple-match list, no match, or terminal-order status. | Future `1.2` / Sam review action. |
| `GET` | `/api/orders/<order_id>` | Return one order with matching `ORDER_LINES` and generated `ORDER_DOCUMENTS` rows. Header includes `payment_method` (from `ORDER_MASTER`), `line_count` (from overview: **all** line rows including cancelled — see `ORDER_OVERVIEW.md`), **`active_line_count`**, **`cancelled_line_count`**, **`active_line_total`**, and **`all_line_total`**. | Web app, `1.2` `get_order_context` branch. |
| `GET` | `/api/reports/daily-summary` | Return daily operational order buckets and counts for n8n/reporting. Optional `?date=YYYY-MM-DD`. | n8n scheduled summary, web app/report tooling. |
| `GET` | `/api/orders/available-pigs` | Return sale-available pigs from `SALES_AVAILABILITY`. | Web app/order tooling. |
| `POST` | `/api/orders/<order_id>/reserve` | Mark order lines as reserved and update master reserved count. | Web app, future steward action. |
| `POST` | `/api/orders/<order_id>/release` | Release reserved order lines and reset master reserved count. | Web app, future cancel/reject flow. |
| `POST` | `/api/orders/<order_id>/send-for-approval` | Mark order pending approval and notify approval workflow. | Web app, `1.2 - Amadeus Order Steward`. |
| `POST` | `/api/orders/<order_id>/approve` | Approve order, then attempt auto-reservation of eligible active lines. | Web app/human action. |
| `POST` | `/api/orders/<order_id>/reject` | Reject approval and mark order cancelled. | Web app/human action. |
| `POST` | `/api/orders/<order_id>/cancel` | Customer-cancel order, cancel linked lines, and release reservations. | Web app, future Order Steward action. |
| `POST` | `/api/orders/<order_id>/complete` | Complete order, collect lines, and update sold/exited pigs. | Web app/human action. |
| `POST` | `/api/master/orders` | Create draft order. | `1.2 - Amadeus Order Steward`, web app. |
| `PATCH` | `/api/master/orders/<order_id>` | Update allowed draft/header fields. | `1.2 - Amadeus Order Steward`, web app. |
| `POST` | `/api/master/orders/<order_id>/sync-lines` | Sync requested items into order lines. | `1.2 - Amadeus Order Steward`. |
| `POST` | `/api/master/order-lines` | Create one order line. | Web app/manual tooling. |
| `PATCH` | `/api/master/order-lines/<order_line_id>` | Update unit price and notes. | Web app/manual tooling. |
| `DELETE` | `/api/master/order-lines/<order_line_id>` | Soft-cancel one line. | Web app/manual tooling. |

## Current `1.2 - Order Steward` Live Actions

The n8n docs currently treat only these actions as live from Sam/`1.0`:

| Steward action | Backend endpoint | Status |
| --- | --- | --- |
| `create_order` | `POST /api/master/orders` | Live |
| `create_order_with_lines` | `POST /api/master/orders` then `POST /api/master/orders/<order_id>/sync-lines` | Live — atomic branch in `1.2` |
| `update_order` | `PATCH /api/master/orders/<order_id>` | Live |
| `sync_order_lines_from_request` | `POST /api/master/orders/<order_id>/sync-lines` | Live |
| `get_order_context` | `GET /api/orders/<order_id>` (read-only; formatted in steward) | Live |
| `get_active_customer_order_context` | `GET /api/orders/active-customer-context` (read-only; backend filtered) | Backend and `1.2` export ready; `1.0` routing planned |
| `cancel_order` | `POST /api/orders/<order_id>/cancel` | Live |
| `send_for_approval` | `POST /api/orders/<order_id>/send-for-approval` | Live — happy path and backend `400` customer-safe reply verified. |

Other backend endpoints may exist and work from the web app, but they should not be treated as active Sam tools until wired, tested, and documented.

## Order Intake State API (Phase 5.5)

These endpoints are backend-ready for persistent intake state. They are not yet live Sam routing truth until Phase 5.6 shadow-mode verification passes.

### Read Intake Context

Endpoint: `GET /api/order-intake/context?conversation_id=<id>`

Returns:

- `lookup_status = single_match` with current intake state and items when an active intake exists.
- `lookup_status = no_match` when no active intake exists.

### Update Intake State

Endpoint: `POST /api/order-intake/update`

Payload shape:

```json
{
  "conversation_id": "1774",
  "account_id": "147387",
  "contact_id": "123",
  "customer_name": "Charl N",
  "customer_phone": "447388223114",
  "customer_channel": "Sam - WhatsApp",
  "customer_language": "English",
  "updated_by": "Sam",
  "patch": {
    "collection_location": "Riversdale",
    "collection_time_text": "Friday at 14:00",
    "payment_method": "Cash",
    "quote_requested": true,
    "order_commitment": true,
    "last_customer_message": "Can I get a quote?"
  },
  "items": [
    {
      "item_key": "item_1",
      "quantity": 1,
      "category": "Grower",
      "weight_range": "35_to_39_Kg",
      "sex": "Female",
      "intent_type": "primary",
      "status": "active"
    }
  ]
}
```

Rules:

- n8n/Sam may propose a patch, but backend validates and merges it.
- Blank patch values do not erase known state.
- Invalid enum values return `400`.
- Existing items are matched by stable `item_key`.
- Removed/replaced items are kept in `ORDER_INTAKE_ITEMS`; they are not deleted.
- Response includes `missing_fields`, `ready_for_draft`, `ready_for_quote`, `next_action`, and `safe_reply_facts`.

### Reset Intake

Endpoint: `POST /api/order-intake/<conversation_id>/reset`

Payload:

```json
{
  "closed_reason": "admin_reset",
  "updated_by": "App"
}
```

This marks the active intake `Closed` and keeps the row for audit/history.

## Active Customer Order Context Lookup

Endpoint: `GET /api/orders/active-customer-context`

Purpose:

- Find a relevant active customer order without exposing the full order list to Sam.
- Support recovery when Chatwoot `order_id` is missing or stale.
- Keep `/api/orders` available for web app/admin only, not as a Sam-facing tool.

Query parameters:

- `order_id` - optional exact order reference. If supplied, this is checked first.
- `conversation_id` - optional Chatwoot conversation ID from `ORDER_MASTER.ConversationId`.
- `customer_phone` - optional customer phone. Non-digit characters are ignored for matching.

At least one of those parameters is required.

Active statuses:

- `Draft`
- `Pending_Approval`
- `Approved`

Terminal statuses such as `Cancelled` and `Completed` are not returned as active context. Exact `order_id` lookup can still return `lookup_status = terminal_order` so Sam can explain that the order is not active.

Response statuses:

- `single_match` - one active order was found; response includes `order_context`.
- `multiple_matches` - more than one active order matched; response includes up to five safe summaries in `matches[]`.
- `no_match` - no active order matched.
- `terminal_order` - exact `order_id` was found but is not active.

Safe context shape:

- `order`: order ID, status fields, request fields, payment method, collection location, active line count, and active line total.
- `line_groups`: grouped active line summary by sale category, weight band, sex, line status, reserved status, and unit price.
- No raw full order list is returned.
- No direct sheet rows are returned.
- No pig IDs or tag numbers are returned in this endpoint.

## Daily Summary Report (Phase 3.1)

Endpoint: `GET /api/reports/daily-summary`

Optional query:

- `date=YYYY-MM-DD` - report date. Defaults to today's server date when omitted.

Returned sections:

- `new_drafts`
- `drafts_missing_payment_method`
- `pending_approval`
- `approved`
- `cancelled_today`
- `completed_today`
- `orders_needing_attention`

Rules:

- `new_drafts`: Draft orders with `Created_At` on the report date.
- `drafts_missing_payment_method`: Draft orders where `Payment_Method` is not `Cash` or `EFT`.
- `pending_approval`: orders currently in `Pending_Approval`.
- `approved`: orders currently `Approved`.
- `cancelled_today`: orders with an `ORDER_STATUS_LOG` transition to `Cancelled` on the report date.
- `completed_today`: orders with an `ORDER_STATUS_LOG` transition to `Completed` on the report date.
- `orders_needing_attention`: Drafts missing payment/location/active lines, pending approvals without active lines, or approved orders where reserved count is below active line count.

n8n should read this endpoint for the scheduled daily summary instead of reading order sheets directly.

## Send For Approval Validation Contract

When `send_for_approval` is called (Phase 1.4), backend must validate all of the following before changing order status:

| Field | Rule |
| --- | --- |
| `Order_Status` | Must be `Draft`. Reject all other statuses. |
| `ORDER_LINES` | At least one non-cancelled line must exist for the order. |
| `PaymentMethod` | Must be `Cash` or `EFT`. Reject if empty or missing. |
| `customer_name` | Must be non-empty. |
| `collection_location` | Must be non-empty. |

Sam must check `order_status`, `payment_method`, and the presence of lines before routing to `send_for_approval` in `1.0`, to give the customer a clear message rather than a backend error.

## Approve / Reject Direction

Current approval behavior:

- `POST /api/orders/<order_id>/approve` represents the human/admin commercial decision to accept the order.
- Approval is allowed only when `Order_Status = Pending_Approval`.
- Draft, Approved, Cancelled, and Completed orders cannot be approved through this endpoint.
- `approve_order` updates approval state first, then attempts to reserve eligible active order lines.
- If reservation fails or partially fails, the approval is not rolled back.
- Backend writes a follow-up warning to `ORDER_STATUS_LOG` and returns `reserve_warning` so the admin web app can surface the manual follow-up.
- The response includes `auto_reserve` with the same line-level summary returned by `POST /api/orders/<order_id>/reserve` when the reservation attempt runs.

Current rejection behavior is documented below. Rejection should cancel/release linked non-cancelled/non-collected lines and should remain blocked for completed orders.

Current customer notification behavior:

- Approval and rejection notifications should be sent by a separate outbound n8n workflow, not by Sam's inbound `1.0` customer-message workflow.
- Backend calls `ORDER_NOTIFICATION_WEBHOOK_URL` after successful approval or rejection when the environment variable is configured.
- Notification webhook delivery is non-blocking with a short timeout; failures are returned as `notification_warning` and written to `ORDER_STATUS_LOG` for manual follow-up.
- The notification workflow looks up the Chatwoot conversation from `ORDER_MASTER.ConversationId`, stored when the draft is created.

## Important Payload Contracts

### Create Order

Endpoint: `POST /api/master/orders`

Important fields:

- `order_date`
- `customer_name`
- `customer_phone`
- `customer_channel`
- `customer_language`
- `order_source`
- `requested_category`
- `requested_weight_range`
- `requested_sex`
- `requested_quantity`
- `quoted_total`
- `notes`
- `created_by`
- `conversation_id` - optional Chatwoot conversation ID. Stored as `ORDER_MASTER.ConversationId` for Phase 1.9 outbound notifications.

Current result includes success state, generated `order_id`, and any warnings.

### Update Order

Endpoint: `PATCH /api/master/orders/<order_id>`

Allowed fields in current validation:

- `requested_quantity`
- `requested_category`
- `requested_weight_range`
- `requested_sex`
- `collection_location`
- `notes`
- `changed_by`
- `payment_method` — API field. Values: `Cash` or `EFT` only. Maps to `ORDER_MASTER.Payment_Method` and is locked once `Order_Status` is beyond `Draft`.

Current validation does not allow arbitrary header updates. Add new fields deliberately.

Payment method lock rule: backend must reject `payment_method` updates when `Order_Status` is `Pending_Approval`, `Approved`, `Completed`, or `Cancelled`. Changes are only permitted while the order is in `Draft` status.

### Sync Lines

Endpoint: `POST /api/master/orders/<order_id>/sync-lines`

Payload:

```json
{
  "changed_by": "Sam",
  "requested_items": [
    {
      "request_item_key": "primary_1",
      "category": "Young Piglets",
      "weight_range": "2_to_4_Kg",
      "sex": "Male",
      "quantity": 2,
      "intent_type": "primary",
      "status": "active",
      "notes": "Customer requested male piglets"
    }
  ]
}
```

Important rules:

- `request_item_key` is required and must remain stable across repeated syncs.
- Split items such as `primary_1` and `primary_2` must both be preserved.
- `intent_type` is optional metadata. If supplied, it must be one of `primary`, `addon`, `nearby_addon`, or `extractor_slot`; it does not alter matching.
- `status` is optional and defaults to `active`. Backend sync rejects any value other than `active`; callers must omit inactive rows instead of sending them.
- Exact-match sync can cancel/recreate lines.
- **Partial/no-match:** when some but not enough stock is available, the backend still creates lines for the matched pigs. Each result row can have `match_status: partial_match`, `matched_quantity`, `available_quantity`, and `alternatives`. When no pigs match an item, the row uses `match_status: no_match`, `matched_quantity: 0`, and may still include alternatives. Top-level `success` means the sync call completed; Sam/n8n must use `complete_fulfillment`, `fulfillment_status`, `requested_total`, `matched_total`, `unmatched_total`, and `incomplete_items` to decide whether the customer request was fully satisfied.

## Quote Document Behavior (Phase 2.3)

### `POST /api/orders/<order_id>/quote`

Generates a quote PDF for an order, uploads it to the configured quote Shared Drive folder, and appends a metadata row to `ORDER_DOCUMENTS`.

Automatic quote readiness:

- `POST /api/master/orders/create-with-lines`, `PATCH /api/master/orders/<order_id>`, and `POST /api/master/orders/<order_id>/sync-lines` attach `auto_quote` after successful order mutations.
- `auto_quote` generates a quote only when the order is quote-ready: Draft status, customer name, collection location, valid `Payment_Method = Cash|EFT`, active order lines, complete active line count versus requested quantity, and valid unit prices.
- Readiness uses `ORDER_MASTER` truth for header fields and can fall back to `ORDER_MASTER` + `ORDER_LINES` while formula-driven `ORDER_OVERVIEW` catches up.
- If the latest non-voided quote already matches the current draft fingerprint, `auto_quote.generated = false` and `reason = latest_quote_current`. The fingerprint uses stable line content, not volatile `Order_Line_ID`.
- If not quote-ready, `auto_quote.missing_fields` explains what is still needed; no PDF is generated.

**Rules:**
- Order must exist.
- Order may be `Draft`, `Pending_Approval`, or `Approved`.
- `Payment_Method` must be `Cash` or `EFT`.
- At least one non-cancelled order line must exist.
- Every active line must have `Unit_Price > 0`.
- Quote versions increment per order (`V1`, `V2`, etc.).
- Draft quotes include the visible note: `Draft quote - subject to availability and approval`.
- `Cash` quotes show VAT amount as `0`.
- `EFT` quotes add VAT using the locked `vat_rate` from `SYSTEM_SETTINGS`.

**Response (success):**
```json
{
  "success": true,
  "message": "Quote generated successfully.",
  "order_id": "ORD-2026-01E18A",
  "document_id": "DOC-2026-49BF16",
  "document_type": "Quote",
  "document_ref": "Q-2026-01E18A",
  "payment_ref": "01E18A",
  "version": 1,
  "file_name": "QUO_2026_05_10_01E18A_V1_(R3,200.00)_Cash.pdf",
  "google_drive_file_id": "1FA50hJUf7q41jKGX3trRcEceaJbfSLk1",
  "google_drive_url": "https://drive.google.com/file/d/...",
  "subtotal_ex_vat": 3200.0,
  "vat_amount": 0.0,
  "total": 3200.0,
  "valid_until": "2026-05-13"
}
```

**HTTP status codes:**
- `201` — quote generated and recorded
- `400` — missing order, missing payment method, no active lines, missing/zero unit price, missing settings, or Drive upload failure

## Invoice Document Behavior (Phase 2.4)

### `POST /api/orders/<order_id>/invoice`

Generates an invoice PDF for an approved/completed order, uploads it to the configured invoice Shared Drive folder, and appends a metadata row to `ORDER_DOCUMENTS`.

**Rules:**
- Order must exist.
- Order must be `Approved` or `Completed`.
- An existing non-voided quote is required.
- The invoice uses the latest non-voided quote version for VAT rate, payment method, subtotal, VAT amount, and total.
- Invoice versions increment per order (`V1`, `V2`, etc.).
- Backend must not recalculate invoice totals independently from the selected quote.

**Response (success):**
```json
{
  "success": true,
  "message": "Invoice generated successfully.",
  "order_id": "ORD-2026-01E18A",
  "document_id": "DOC-2026-EC0265",
  "document_type": "Invoice",
  "document_ref": "INV-2026-01E18A",
  "payment_ref": "01E18A",
  "version": 1,
  "source_quote_document_id": "DOC-2026-45F259",
  "source_quote_ref": "Q-2026-01E18A-V3",
  "file_name": "INV_2026_05_10_01E18A_V1_(R3,680.00)_EFT.pdf",
  "google_drive_file_id": "1w5peZn-imS-t0p7BAwTd2fIWWGPg2Dgq",
  "google_drive_url": "https://drive.google.com/file/d/...",
  "subtotal_ex_vat": 3200.0,
  "vat_amount": 480.0,
  "total": 3680.0
}
```

**HTTP status codes:**
- `201` — invoice generated and recorded
- `400` — missing order, ineligible order status, missing non-voided quote, invalid quote totals/settings, or Drive upload failure

## Document Delivery Behavior (Phase 2.5)

### `POST /api/order-documents/<document_id>/send`

Triggers outbound n8n delivery for an existing generated document.

Payload:

```json
{
  "conversation_id": "1742",
  "sent_by": "Codex Phase 2.5 Test",
  "account_id": "147387"
}
```

Rules:

- `conversation_id` is required; backend does not fall back to the order's customer conversation.
- Voided documents cannot be sent.
- Backend calls `DOCUMENT_DELIVERY_WEBHOOK_URL`.
- Backend marks `ORDER_DOCUMENTS.Document_Status = Sent` only if the workflow confirms success.

For Phase 2.5 live tests, use `conversation_id = 1742` only.

## Reserve And Release Behavior (Phase 1.6)

### `POST /api/orders/<order_id>/reserve`

Marks eligible order lines as reserved and updates `ORDER_MASTER.Reserved_Pig_Count`.

**Eligibility rules:**
- Lines with `Line_Status = Cancelled` or `Collected` are skipped (terminal states).
- Lines with no `Pig_ID` are skipped — placeholder lines cannot hold inventory.
- Lines already at `Reserved_Status = Reserved` and `Line_Status = Reserved` are a noop (idempotent).
- All other active lines with a `Pig_ID` are reserved in one batch write.

**HTTP status codes:**
- `200` — success (at least one line is or was already reserved)
- `400` — order not found, empty sheet, or missing column
- `422` — no eligible lines to reserve (all cancelled, collected, or missing pig)

**Response (success):**
```json
{
  "success": true,
  "order_id": "ORD-...",
  "reserved_pig_count": 3,
  "changed_count": 2,
  "message": "Order lines reserved successfully.",
  "warning": "Some lines could not be reserved: 1 line(s) skipped (no_pig_assigned).",
  "line_results": [
    { "order_line_id": "OL-...", "pig_id": "PIG-001", "action": "reserved" },
    { "order_line_id": "OL-...", "pig_id": "PIG-002", "action": "noop", "reason": "already_reserved" },
    { "order_line_id": "OL-...", "pig_id": "", "action": "skipped", "reason": "no_pig_assigned" },
    { "order_line_id": "OL-...", "pig_id": "PIG-003", "action": "skipped", "reason": "terminal_line_status" }
  ]
}
```

`warning` is present only when some lines were skipped but others were successfully reserved or already reserved.

**Response (failure — 422):**
```json
{
  "success": false,
  "order_id": "ORD-...",
  "reserved_pig_count": 0,
  "changed_count": 0,
  "message": "No lines could be reserved.",
  "errors": ["No eligible lines to reserve. All lines are either cancelled, collected, or have no pig assigned."],
  "line_results": [...]
}
```

---

### `POST /api/orders/<order_id>/release`

Releases all reserved order lines and updates `ORDER_MASTER.Reserved_Pig_Count`.

**Rules:**
- `Collected` lines are terminal — never touched.
- `Reserved_Status` is cleared to `Not_Reserved` only where it equals `Reserved`.
- `Line_Status` is reverted from `Reserved` to `Draft` only for active lines (`Cancelled` lines keep their status).
- Calling release twice is safe — second call returns all noops and `success: true`.
- `Reserved_Pig_Count` is set to the actual post-release count (not a blind `0`).

**HTTP status codes:**
- `200` — always on success (idempotent)
- `400` — order not found, empty sheet, or missing column

**Response:**
```json
{
  "success": true,
  "order_id": "ORD-...",
  "reserved_pig_count": 0,
  "changed_count": 2,
  "message": "Order reservations released successfully.",
  "line_results": [
    { "order_line_id": "OL-...", "pig_id": "PIG-001", "action": "released" },
    { "order_line_id": "OL-...", "pig_id": "PIG-002", "action": "released" },
    { "order_line_id": "OL-...", "pig_id": "", "action": "noop" },
    { "order_line_id": "OL-...", "pig_id": "PIG-003", "action": "skipped", "reason": "terminal_line_status" }
  ]
}
```

`changed_count` reflects rows written to `ORDER_LINES`. On a second release call, `changed_count = 0` and all line results are `noop`.

---

## Reject And Cancel Behavior

Current reject endpoint behavior:

- sets `ORDER_MASTER.Order_Status = Cancelled`
- sets `ORDER_MASTER.Approval_Status = Rejected`
- cancels linked non-cancelled/non-collected order lines
- sets linked line `Reserved_Status` values to `Not_Reserved`
- resets `ORDER_MASTER.Reserved_Pig_Count` to `0`
- appends `ORDER_STATUS_LOG` when rejection or cleanup changes state
- blocks completed orders from being rejected

Current customer cancel endpoint behavior:

- `POST /api/orders/<order_id>/cancel` sets `Order_Status = Cancelled`.
- It sets `Approval_Status = Not_Required`.
- It sets `Payment_Status = Cancelled`.
- It cancels linked non-cancelled/non-collected order lines.
- It sets linked line `Reserved_Status` values to `Not_Reserved`.
- It resets `ORDER_MASTER.Reserved_Pig_Count` to `0`.
- It writes `ORDER_STATUS_LOG` when cancellation or cleanup changes state.
- It blocks completed orders from being cancelled.
- It does not convert already rejected orders into customer-cancelled orders.

## Order Review Direction

Sam should preferably request order context through `1.2 - Amadeus Order Steward` and backend review endpoints, not by directly reading `ORDER_OVERVIEW` as a production tool.

Reason:

- backend can verify customer/order ownership
- backend can filter the fields Sam receives
- backend can avoid exposing irrelevant orders
- backend responses are easier to test than direct AI sheet access
