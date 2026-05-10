# API Structure

## Purpose

Documents the current Flask order API used by the web app and n8n workflows.

All order API routes are registered under `/api`.

## Route Summary

| Method | Path | Current purpose | Main caller |
| --- | --- | --- | --- |
| `GET` | `/api/orders` | List orders from `ORDER_OVERVIEW`. | Web app, future review tooling. |
| `GET` | `/api/orders/<order_id>` | Return one order with matching `ORDER_LINES`. Header includes `payment_method` (from `ORDER_MASTER`), `line_count` (from overview: **all** line rows including cancelled — see `ORDER_OVERVIEW.md`), and **`active_line_count`** (non-cancelled lines only, matches send-for-approval eligibility). | Web app, `1.2` `get_order_context` branch. |
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
| `cancel_order` | `POST /api/orders/<order_id>/cancel` | Live |
| `send_for_approval` | `POST /api/orders/<order_id>/send-for-approval` | Live — happy path and backend `400` customer-safe reply verified. |

Other backend endpoints may exist and work from the web app, but they should not be treated as active Sam tools until wired, tested, and documented.

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
- Exact-match sync can cancel/recreate lines.
- **Partial match:** when some but not enough stock is available, the backend still creates lines for the matched pigs. Each result row can have `match_status: partial_match`, `matched_quantity` (fulfilled count), `available_quantity` (candidates matching filters), and the top-level response includes `partial_fulfillment: true` when any row was partial. Sam/n8n must not treat that as full quantity satisfaction.

## Quote Document Behavior (Phase 2.3)

### `POST /api/orders/<order_id>/quote`

Generates a quote PDF for an order, uploads it to the configured quote Shared Drive folder, and appends a metadata row to `ORDER_DOCUMENTS`.

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
