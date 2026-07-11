# Order Data Model

Order source-of-truth includes orders, order lines, order intakes, order intake items, order documents, order status logs, and sales pricing where migrated.

Backend owns order logic, validation, reservations, lifecycle changes, and safe writes.

## Core Entities

| Entity | Current/legacy source | Supabase target | Purpose |
| --- | --- | --- | --- |
| Order header | `ORDER_MASTER` | `orders` | Customer/order lifecycle, approval, payment, collection, conversation link. |
| Order lines | `ORDER_LINES` | `order_lines` | Pig/product line items, reservation state, price snapshot, request item key. |
| Intake header | `ORDER_INTAKE_STATE` | `order_intakes` | Conversation/order-intake memory before or beside a draft order. |
| Intake items | `ORDER_INTAKE_ITEMS` | `order_intake_items` | Requested item rows, split sex/category requests, matched/removed history. |
| Documents | `ORDER_DOCUMENTS` | `order_documents` | Quote/invoice metadata, PDF/Drive link, send state, VAT/payment snapshot. |
| Status log | `ORDER_STATUS_LOG` | `order_status_logs` | Append-only order lifecycle audit. |
| Pricing | `SALES_PRICING` | `sales_pricing` | Effective-dated sales price reference. |
| Sales transaction | none / Supabase | `sales_transactions` | Explicit income/sale value records. Do not infer Rand value from pig count. |
| Sales item | none / Supabase | `sales_transaction_items` | Pigs/carcasses/cuts/items attached to one sale transaction. |

## Field Rules

- `Order_ID`, `Order_Line_ID`, document refs, and payment refs must remain stable public identifiers.
- `Request_Item_Key` must be stable across repeated syncs or split-item orders can duplicate/drift.
- `intent_type` is metadata only. It must not replace `request_item_key`.
- `requested_items[].status` must be `active`; inactive/cancelled requested items should be omitted by callers.
- Historical line prices must not change when `SALES_PRICING` changes later.
- `ORDER_STATUS_LOG` / `order_status_logs` is append-only for normal operations.
- Documents preserve VAT/payment snapshots; invoices must not recalculate totals independently from the selected quote.

## Lifecycle Rules

- Draft creation and line sync must happen through backend APIs.
- `send_for_approval` requires Draft status, customer name, payment method, collection location, and at least one active line.
- Approval may attempt auto-reservation, but reservation warnings do not roll back the approval automatically.
- Approved live-stock orders may be revised only through the explicit approved livestock revision action. Normal line sync remains draft-only; the revision action must update the order header/lines, reserve current active lines, regenerate required documents with an idempotency fingerprint, send owner paperwork only, and prepare customer quote send context unless a separate confirmed owner send payload is present.
- Rejection/customer cancellation must cancel/release linked non-terminal lines and write status-log evidence.
- Completed orders and terminal records must be protected from unsafe approval/rejection/cancellation changes.
- Quote/document sending must use backend-prepared document state and the outbound document-delivery path.

## Sales Transaction Rules

- `gross_total`, `deductions_total`, and `net_total` must be explicit values.
- Do not calculate income from pig count alone.
- Slaughter/abattoir sales may be recorded without a normal customer order.
- Meat/carcass sales should use the same transaction family once the meat workflow is ready.
- Duplicate non-cancelled sale records for the same pig must be blocked.

## Source References

- `docs/02-backend/DATA_MODELS.md`
- `docs/02-backend/API_STRUCTURE.md`
- `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`
- `docs/03-google-sheets/SHEET_SCHEMA.md`
- `docs/03-google-sheets/WRITE_OWNERSHIP.md`
