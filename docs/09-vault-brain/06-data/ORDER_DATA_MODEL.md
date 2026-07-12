# Order Data Model

## Live-Stock Price Snapshot Rule

- Herdmaster/farm data supplies the selected pig's current category, weight band, sex, weight, and availability truth.
- SAM Pricing resolves the active Supabase `sales_pricing` rule for that classification.
- Orders snapshot the resolved unit price onto the order line when the animal is added or before the first quote is generated.
- A blank or zero-priced active line must be repaired from the current price list before quote generation; the owner must not be required to type routine prices.
- Existing positive order-line prices remain frozen. Repricing requires an explicit owner action so an old quote cannot change silently.
- If no matching active rule exists, quote generation fails closed and identifies the exact affected line and classification.

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
- Approved live-stock order revisions must use a dedicated owner/Oom Sakkie backend action. That action must require explicit owner/Oom Sakkie authorization before mutation (`owner_authorized=true` or exact `owner_confirmation='REVISE APPROVED LIVESTOCK ORDER'`, with `authorization_source` and a trusted `changed_by` actor). After that gate, it may update the approved order request, resync active lines under the explicit approved-order revision status override, reserve the corrected active lines, regenerate current paperwork, and prepare a customer quote send packet, but customer sending still requires a separate owner confirmation.
- Approved-order revision actions must be idempotent: repeated correction requests should detect already-matching active lines and logged revision fingerprints instead of silently duplicating pigs or paperwork.
- `send_for_approval` requires Draft status, customer name, payment method, collection location, and at least one active line.
- Approval may attempt auto-reservation, but reservation warnings do not roll back the approval automatically.
- Rejection/customer cancellation must cancel/release linked non-terminal lines and write status-log evidence.
- Completed orders and terminal records must be protected from unsafe approval/rejection/cancellation changes.
- Quote/document sending must use backend-prepared document state and the outbound document-delivery path.

## Sales Transaction Rules

- `gross_total`, `deductions_total`, and `net_total` must be explicit values.
- Every Completed Supabase-backed order reconciles to exactly one sales transaction keyed by `linked_order_id`; repeated completion is projection-only and does not repeat pig lifecycle or status-log writes.
- Projection atomically reconciles only Collected lines by `(sale_id, order_line_id)`. Slaughter/abattoir context takes stream precedence, then meat/carcass/pork, otherwise Livestock.
- Collected line snapshots form `gross_total`; order `final_total` forms `net_total` when present and the difference is explicit deductions. An unexplained final total above line snapshots blocks projection. POP or unknown payment evidence remains `Unpaid`.
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
