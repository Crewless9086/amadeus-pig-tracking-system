# Supabase Order Schema Plan

## Purpose

Phase 10.2 planning document.

This document turns the Phase 7.2 database scaling draft into a first implementation boundary for orders/sales data in Supabase/Postgres.

This plan has moved through the first shadow-import slice. It does not approve live route cutover.

## Current Status

- Phase 10.1A database connection is deployed and verified.
- Phase 10.1B baseline migration is deployed and verified.
- Phase 10.2A order/sales tables are created and verified.
- Phase 10.2D completed-order shadow import is applied and verified.
- Phase 10.2F read-only shadow comparison endpoint is deployed and verified.
- Phase 10.2G sales transaction extension is being planned; no SQL migration has been approved yet.
- Phase 10.2H sales transaction empty-table migration is deployed and verified.
- Phase 10.2I read-only sales transaction API is deployed and verified.
- Phase 10.2J sales transaction dry-run validator is deployed and verified.
- Phase 10.2K real create flow is planned only; no write endpoint has been added.
- Supabase now contains the internal migration log plus the first order/sales boundary tables.
- Supabase contains shadow order/sales data only for the approved completed-order batch.
- No pig, customer, telemetry, or broader business tables have been created.
- Google Sheets remains the live source of truth.
- Owner reviewed and accepted this plan on 2026-05-21.

## Recommended 10.2 Boundary

First business schema boundary:

1. `orders`
2. `order_lines`
3. `order_intakes`
4. `order_intake_items`
5. `order_documents`
6. `order_status_logs`
7. `sales_pricing`

Planned extension after the first boundary:

8. `sales_transactions`
9. `sales_transaction_items`

Do not include yet:

- `PIG_MASTER`
- `WEIGHT_LOG`
- `MATING_LOG`
- `LITTERS`
- `SALES_AVAILABILITY`
- `SYSTEM_SETTINGS`
- weather logs
- Sunsynk logs
- irrigation logs

Reason:

- Orders/sales already have the strongest documented schema.
- Existing business logic is backend-owned and tested.
- This boundary gives useful value without forcing the full piggery data model into Supabase immediately.
- Telemetry needs a different time-series design and remains Phase 10.3.

## Source Sheet Mapping

| Google Sheet | Supabase Table | 10.2 Role |
| --- | --- | --- |
| `ORDER_MASTER` | `orders` | Order header and lifecycle state. |
| `ORDER_LINES` | `order_lines` | Line-level sales/reservation state. |
| `ORDER_INTAKE_STATE` | `order_intakes` | Conversation intake header state. |
| `ORDER_INTAKE_ITEMS` | `order_intake_items` | Conversation requested item rows. |
| `ORDER_DOCUMENTS` | `order_documents` | Quote/invoice metadata and send state. |
| `ORDER_STATUS_LOG` | `order_status_logs` | Append-only order audit trail. |
| `SALES_PRICING` | `sales_pricing` | Effective-dated pricing reference. |

Read-only/helper sheets for later:

| Sheet/View | 10.2 Treatment |
| --- | --- |
| `ORDER_OVERVIEW` | Replace later with API read models over Supabase; keep while Sheets is live. |
| `SALES_AVAILABILITY` | Keep in Sheets until pig/stock data migration; order matching still depends on pig availability. |
| `SYSTEM_SETTINGS` | Keep in Sheets initially for document settings; app settings table can come later. |
| `PIG_MASTER` | Keep in Sheets for completion/sold state until pig migration phase. |

## Table Ownership

### `orders`

Owns the order header state currently stored in `ORDER_MASTER`.

Must preserve:

- public `order_id`, for example `ORD-2026-46D437`
- lifecycle fields: order, approval, payment
- payment method
- collection details
- Chatwoot `conversation_id`
- created/updated audit fields
- import traceability

### `order_lines`

Owns order line state currently stored in `ORDER_LINES`.

Must preserve:

- public/stable `order_line_id`
- `order_id` link
- `pig_id` when selected
- tag snapshot
- sale category, weight band, sex
- unit price snapshot
- line status and reserved status
- request item key
- import traceability

Important rule:

- Historical line prices must not change when `sales_pricing` changes later.

### `order_intakes`

Owns conversation intake header state currently stored in `ORDER_INTAKE_STATE`.

Must preserve:

- `intake_id`
- Chatwoot conversation/contact identity
- linked draft order
- intake lifecycle state
- known non-item facts
- missing fields / next action / readiness fields
- closed reason and audit data

### `order_intake_items`

Owns requested item rows currently stored in `ORDER_INTAKE_ITEMS`.

Must preserve:

- `intake_item_id`
- `intake_id`
- stable `item_key`
- quantity/category/weight/sex
- active/removed/replaced history
- linked order line IDs
- match status and matched quantity

Important rule:

- Removed/replaced rows should remain as history. Do not delete them during import.

### `order_documents`

Owns quote/invoice metadata currently stored in `ORDER_DOCUMENTS`.

Must preserve:

- `document_id`
- `order_id`
- document type/reference/version/status
- payment reference
- payment method and VAT snapshot
- subtotal/VAT/total snapshot
- valid-until date
- Google Drive file ID/URL/filename
- sent state

Important rule:

- PDFs can remain in Google Drive initially. Supabase stores metadata first.

### `order_status_logs`

Owns order lifecycle audit trail currently stored in `ORDER_STATUS_LOG`.

Must preserve:

- status log ID where available
- order ID
- status date
- old/new status
- actor/source
- notes
- created timestamp

Important rule:

- This table is append-only for normal operations.

### `sales_pricing`

Owns pricing currently stored in `SALES_PRICING`.

Change from Sheets:

- Add stable `pricing_id`.
- Add effective dates.
- Add active flag.
- Add currency, default `ZAR`.
- Keep copied price snapshot on `order_lines`.

Pricing selection rule:

1. Match category and weight band.
2. Match sex if a sex-specific price exists; otherwise use general price.
3. Use active prices only.
4. Use the newest price where `effective_from <= order/quote date`.
5. Ignore prices where `effective_to` is set and before the order/quote date.
6. Copy `unit_price` and `pricing_id` to the order line.

## 10.2G Sales Transaction Extension Plan

Purpose:

- create a proper source of truth for sales transactions and Rand values
- support livestock, slaughter/abattoir, and future meat/carcass sales with one transaction model
- avoid calculating income from pig exit counts
- keep dashboard Rand totals blocked until explicit transaction/value records exist

Reason:

- `PIG_MASTER` exits are useful for counting pigs/items that left the farm.
- `PIG_MASTER` exits are not a reliable income ledger.
- Completed livestock orders can have one order total covering many pigs.
- Slaughter/abattoir sales may happen without a normal customer order.
- Future meat/carcass sales need weights, products, deductions, delivery, and payment state.

Recommended tables:

1. `sales_transactions`
2. `sales_transaction_items`

### `sales_transactions`

Owns the sale header and money fields.

Recommended fields:

| Field | Type direction | Notes |
| --- | --- | --- |
| `sale_id` | text primary key | Public stable ID, for example `SALE-2026-...`. |
| `sale_date` | timestamptz/date | Business sale date. |
| `sale_stream` | text | `Livestock`, `Slaughter`, or `Meat`. |
| `buyer_name` | text | Customer, abattoir, butcher, or destination name. |
| `buyer_phone_raw` | text | Optional. |
| `buyer_phone_normalized` | text | Optional lookup field. |
| `destination` | text | Useful for abattoir/butcher/collection destination. |
| `linked_order_id` | text nullable FK to `orders.order_id` | Used for livestock orders and future order-backed meat sales. |
| `pig_count` | integer | Snapshot count for quick dashboard reads. |
| `gross_total` | numeric(12,2) | Sale value before deductions. |
| `deductions_total` | numeric(12,2) | Transport, slaughter, processing, commission, or similar. |
| `net_total` | numeric(12,2) | Income after deductions. |
| `currency` | text | Default `ZAR`. |
| `payment_status` | text | Example: `Unpaid`, `Deposit_Paid`, `Paid`, `Part_Paid`, `Cancelled`. |
| `payment_method` | text | Cash, EFT, account, etc. |
| `sale_status` | text | Example: `Draft`, `Confirmed`, `Completed`, `Cancelled`. |
| `notes` | text | Operator notes. |
| `created_by` | text | Actor/operator. |
| `created_at` | timestamptz | Default `now()`. |
| `updated_at` | timestamptz | Default `now()`. |
| `source_sheet_row` | integer | Only if imported from a temporary sheet later. |
| `import_batch_id` | text | Import traceability. |

Important rules:

- Do not infer `gross_total`, `deductions_total`, or `net_total` from pig count.
- A completed livestock order may later create or link one `sales_transactions` row using the trusted order total.
- A slaughter/abattoir sale should be entered as its own transaction even when there is no customer order.
- Meat/carcass sales should use the same transaction family, not a separate one-off table.

### `sales_transaction_items`

Owns the animals/products/weights attached to one sale.

Recommended fields:

| Field | Type direction | Notes |
| --- | --- | --- |
| `sale_item_id` | text primary key | Public stable ID. |
| `sale_id` | text FK to `sales_transactions.sale_id` | Parent transaction. |
| `item_type` | text | `Pig`, `Carcass`, `Cut`, `Box`, `Other`. |
| `pig_id` | text nullable | Links to the pig where applicable. Keep as text until pig master is migrated. |
| `tag_number` | text | Snapshot for operator readability. |
| `order_line_id` | text nullable FK to `order_lines.order_line_id` | Useful for livestock order links. |
| `description` | text | Product/animal description. |
| `quantity` | numeric | Usually 1 for pig, variable for meat items. |
| `live_weight_kg` | numeric(10,3) | Where known. |
| `carcass_weight_kg` | numeric(10,3) | Where known. |
| `packed_weight_kg` | numeric(10,3) | Future meat/carcass use. |
| `unit_price` | numeric(12,2) | Per pig, per kg, or per item depending on pricing basis. |
| `pricing_basis` | text | `Per_Pig`, `Per_Kg_Live`, `Per_Kg_Carcass`, `Per_Item`, etc. |
| `line_total` | numeric(12,2) | Snapshot total for this item. |
| `notes` | text | Item-level notes. |
| `created_at` | timestamptz | Default `now()`. |
| `updated_at` | timestamptz | Default `now()`. |

Important rules:

- Item rows preserve historical sale details even if pig status, pricing, or product definitions change later.
- `pig_id` should remain nullable because future meat boxes/cuts may not map cleanly to one pig.
- The sum of item `line_total` values should reconcile to transaction `gross_total`, allowing explicit rounding/adjustment where needed.

First use case:

- Slaughter/abattoir transaction logging.
- Minimum fields for a useful first record:
  - sale date
  - stream = `Slaughter`
  - buyer/destination
  - pig IDs/tags
  - pig count
  - total amount
  - payment status
  - notes

Later use cases:

- Auto-link completed livestock orders to a transaction row.
- Add carcass/meat sales under Phase 11.
- Add dashboard Rand totals once transaction records exist.
- Add payment tracking and deductions reporting.

Non-goals for 10.2G:

- Do not change the live dashboard Rand values yet.
- Do not cut over order reads/writes to Supabase.
- Do not migrate `PIG_MASTER` yet.
- Do not build the Phase 11 pork/meat sales workflow here.
- Do not create temporary Google Sheets-only transaction logic unless a real sale must be captured before Supabase entry is ready.

Owner decisions and guided defaults before SQL migration:

- Use constrained values now for `sale_stream`, `payment_status`, `sale_status`, `item_type`, and `pricing_basis`.
- Create tables and backend verification first. Build the slaughter sale form after the schema is safely applied and verified.
- Later, completed livestock orders should automatically create or link a `sales_transactions` row where applicable, but do not add automation in the empty-table migration.
- Keep deductions as a single `deductions_total` on the first table. Plan a future child table such as `sales_transaction_deductions` when detailed deductions are needed.
- Include `buyer_phone_raw` and `buyer_phone_normalized` now.
- Add a future customer table to the roadmap before deeper customer/payment reporting.

## 10.2H Sales Transaction Empty-Table Migration

Purpose:

- create only the approved empty sales transaction tables
- add a backend health verifier for the new tables
- keep current app behavior unchanged

Migration:

- `supabase/migrations/202605210003_create_sales_transaction_tables.sql`

Creates:

1. `sales_transactions`
2. `sales_transaction_items`

Does not create:

- pig tables
- customer tables
- deduction child tables
- dashboard Rand values
- live order cutover
- slaughter sale form

Backend verifier:

- `GET /health/database/sales-transaction-schema`

Expected deployed result after SQL is applied:

- `success = true`
- `status = ok`
- `migration_id = 202605210003_create_sales_transaction_tables`
- `missing_tables = []`

Implementation state:

- SQL migration prepared locally.
- Backend verifier route prepared locally.
- Local verification passed on 2026-05-21: focused database tests passed at 12 tests.
- Full local unittest suite passed on 2026-05-21 at 169 tests.
- Deployed verification passed on 2026-05-21: owner ran the SQL migration and `/health/database/sales-transaction-schema` returned `success = true`, `status = ok`, migration ID `202605210003_create_sales_transaction_tables`, both expected tables found, and `missing_tables = []`.
- No backend/dashboard/order behavior changed.

## 10.2I Read-Only Sales Transaction API

Purpose:

- prove the backend can read the new sales transaction tables
- expose a safe backend-only API contract before any write form exists
- keep all dashboard/order behavior unchanged

Endpoint:

- `GET /api/sales-transactions`

Query parameters:

- `sale_stream` optional: `Livestock`, `Slaughter`, or `Meat`
- `limit` optional: defaults to `50`, maximum `100`

Response shape:

- `success`
- `status`
- `count`
- `limit`
- `sale_stream`
- `sales_transactions`
- `source`

Safety rules:

- Reads Supabase only.
- Writes nothing to Supabase.
- Writes nothing to Google Sheets.
- Does not power any dashboard Rand totals yet.
- Does not create livestock transactions automatically.
- Does not create slaughter sale records yet.

Implementation state:

- Read service added: `modules/sales/sales_transaction_read.py`.
- Route added: `GET /api/sales-transactions`.
- Local missing-config route smoke returns safe `503` / `not_configured`.
- Local verification passed on 2026-05-21: focused sales transaction/database tests passed at 17 tests.
- Full local unittest suite passed on 2026-05-21 at 174 tests.
- Deployed verification passed on 2026-05-21: `GET /api/sales-transactions` returned `success = true`, `status = ok`, `count = 0`, empty `sales_transactions`, and read-only source flags.
- No records, write form, dashboard Rand totals, or order automation were added.

## 10.2J Sales Transaction Dry-Run Validator

Purpose:

- validate the first slaughter/abattoir transaction payload shape without writing any data
- calculate gross, deductions, net total, item count, and pig count from submitted payload
- prove the contract before enabling a real create endpoint

Endpoint:

- `POST /api/sales-transactions/dry-run`

Required minimum payload:

```json
{
  "sale_date": "2026-05-21",
  "sale_stream": "Slaughter",
  "buyer_name": "Abattoir",
  "items": [
    {
      "item_type": "Pig",
      "pig_id": "PIG-...",
      "quantity": 1,
      "unit_price": 1200,
      "pricing_basis": "Per_Pig"
    }
  ]
}
```

Safety rules:

- Does not connect to Supabase.
- Writes nothing to Supabase.
- Writes nothing to Google Sheets.
- Does not create sale IDs.
- Does not change pig/order/dashboard state.
- Returns `mode = dry_run` and `source.writes_to_supabase = false`.

Implementation state:

- Validation added in `modules/sales/sales_transaction_validation.py`.
- Dry-run service added in `modules/sales/sales_transaction_dry_run.py`.
- Route added: `POST /api/sales-transactions/dry-run`.
- Local route smoke passed with a valid slaughter payload.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 8 tests.
- Full local unittest suite passed on 2026-05-21 at 177 tests.
- Deployed verification passed on 2026-05-21: dry-run slaughter payload returned `success = true`, `mode = dry_run`, `gross_total = 1200`, `deductions_total = 100`, `net_total = 1100`, and both write flags remained false.
- No real create endpoint, sale IDs, dashboard Rand totals, order automation, or pig status changes were added.

## 10.2K Controlled Sales Transaction Create Flow Plan

Purpose:

- enable the first real Supabase write for sales transactions
- start with a narrow slaughter/abattoir use case
- keep the write atomic, auditable, and isolated from existing Google Sheets behavior

First write endpoint:

- `POST /api/sales-transactions`

Initial scope:

- `sale_stream = Slaughter` only.
- Internal/operator use only.
- Supabase write only.
- No Google Sheets writes.

Current real slaughter workflow:

- Buyer/butcher is currently `JC Slaghuis`.
- Pigs are selected on farm, then transported to `Bartelsfontein` abattoir.
- Carcass weight may be supplied by the abattoir/butcher, but this is not guaranteed.
- Payment normally arrives roughly two weeks later from the butcher.
- Payment method is bank transfer/EFT and the sale must be treated as VAT-relevant.
- Recent real candidate: pig `S10` was reported on 2026-05-21 as recently slaughtered and has been marked as slaughtered in Google Sheets. Use it later only after the create/cancel flow is proven.

Recommended status handling for this workflow:

- When pigs are delivered/slaughtered but payment has not arrived, create the transaction as `sale_status = Confirmed` and `payment_status = Unpaid`.
- When JC Slaghuis pays by bank transfer, update later to `sale_status = Completed` and `payment_status = Paid`.
- Carcass weight should be optional in the first slaughter write flow.
- Until VAT-specific fields are added, `gross_total` and `net_total` should be treated as the actual Rand amounts recorded for the transaction. Before dashboard financial reporting, add/confirm VAT handling fields such as VAT-inclusive/exclusive basis, VAT rate, and VAT amount.

Required fields:

- `sale_date`
- `sale_stream = Slaughter`
- `buyer_name` or `destination`
- at least one item
- every `Pig` item must have `pig_id`
- each item must have either:
  - `line_total`, or
  - `quantity` plus `unit_price`
- `payment_status`

Backend-generated fields:

- `sale_id`, for example `SALE-2026-...`
- `sale_item_id` values
- `pig_count`
- `gross_total`
- `deductions_total`
- `net_total`
- `currency = ZAR`
- `created_at` / `updated_at`

Write behavior:

- Insert one `sales_transactions` row.
- Insert one or more `sales_transaction_items` rows.
- Use one database transaction: header and items must succeed together or roll back together.
- Return `writes_to_supabase = true`.
- Return `writes_to_sheets = false`.

Duplicate protection:

- Block if any submitted `pig_id` already appears in a non-cancelled sales transaction item.
- Non-cancelled means parent `sales_transactions.sale_status` is not `Cancelled`.
- No override behavior in the first write slice.
- If an accidental transaction must be reversed, add a cancel/void flow later rather than deleting rows.

Must not do in first write slice:

- Do not update `PIG_MASTER`.
- Do not change `PIG_OVERVIEW`.
- Do not connect dashboard Rand totals.
- Do not auto-create transactions from completed livestock orders.
- Do not build the web form yet.
- Do not support `Livestock` or `Meat` writes yet.
- Do not create deduction child rows.

Response contract:

- `success`
- `status`
- `sale_id`
- `created_counts`
- `sales_transaction`
- `items`
- `source.writes_to_supabase = true`
- `source.writes_to_sheets = false`

Failure contract:

- Validation errors return `400`.
- Duplicate pig use returns `409`.
- Database failures return safe `503` with no connection string or secrets.
- Failed writes must roll back.

Recommended implementation split:

1. **10.2K1 backend create service and route** - implemented locally 2026-05-21: `POST /api/sales-transactions` supports `Slaughter` only, validates payloads, requires `created_by`, writes header/items atomically to Supabase, blocks duplicate pig IDs, and does not write to Google Sheets.
2. **10.2K2 deployed write test with safe synthetic pig IDs** - verified 2026-05-21 with synthetic pig `PIG-TEST-102K2-20260521` and transaction `SALE-2026-F17E16`.
3. **10.2K3 cancellation/void flow** - deployed and verified 2026-05-21: `POST /api/sales-transactions/<sale_id>/cancel` marks the transaction `Cancelled`, sets `payment_status = Cancelled`, appends an audit note, and never hard-deletes rows.
4. **10.2L internal slaughter sale form** - implemented locally 2026-05-21 at `/sales/slaughter`; it uses the verified sales transaction create/cancel endpoints and does not write Google Sheets.
5. **10.2M dashboard Rand totals** - only after real transactions exist and cancellation behavior is defined.

Implementation state:

- 10.2K1 is deployed and verified.
- New backend module: `modules/sales/sales_transaction_create.py`.
- New route: `POST /api/sales-transactions`.
- Local missing-config route smoke returned safe `503` with no Supabase write.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 15 tests.
- Full local unittest suite passed on 2026-05-21 at 184 tests.
- Deployed 10.2K2 write test passed on 2026-05-21: `POST /api/sales-transactions` created synthetic transaction `SALE-2026-F17E16` for `PIG-TEST-102K2-20260521`.
- Deployed readback passed: `GET /api/sales-transactions?sale_stream=Slaughter&limit=10` returned the synthetic transaction with `payment_status = Unpaid`, `sale_status = Confirmed`, `gross_total = 1200`, and `writes_to_supabase = false`.
- Deployed duplicate guard passed: second create attempt for `PIG-TEST-102K2-20260521` returned `409 duplicate_pig` and `writes_to_supabase = false`.
- No real `S10` transaction has been written.
- 10.2K3 is deployed and verified.
- New route: `POST /api/sales-transactions/<sale_id>/cancel`.
- Cancel requires `cancelled_by` and `cancel_reason`.
- Cancel writes only to Supabase, never deletes rows, and never writes Google Sheets.
- Cancelled transactions are excluded from duplicate-pig blocking because duplicate protection already checks parent `sale_status <> 'Cancelled'`.
- Local missing-config route smoke returned safe `503` with no Supabase write.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 20 tests.
- Full local unittest suite passed on 2026-05-21 at 191 tests.
- Deployed cancellation passed on 2026-05-21: synthetic transaction `SALE-2026-F17E16` was cancelled with `sale_status = Cancelled`, `payment_status = Cancelled`, and an audit note.
- Reuse check passed: after cancelling `SALE-2026-F17E16`, the same synthetic pig ID `PIG-TEST-102K2-20260521` was accepted in new synthetic transaction `SALE-2026-28EF1B`.
- Cleanup passed: synthetic reuse transaction `SALE-2026-28EF1B` was cancelled.
- Final readback shows both synthetic slaughter transactions are cancelled and no active synthetic slaughter transaction remains.
- No real `S10` transaction has been written.
- 10.2L is implemented locally and not yet deployed.
- New page route: `/sales/slaughter`.
- New template/script: `templates/slaughter-sale.html` and `static/js/slaughterSale.js`.
- The form defaults to `JC Slaghuis`, `Bartelsfontein`, `payment_status = Unpaid`, `sale_status = Confirmed`, and `payment_method = EFT`.
- The form loads active pigs from `GET /api/pig-weights/pigs`, creates slaughter transactions through `POST /api/sales-transactions`, lists recent slaughter transactions through `GET /api/sales-transactions?sale_stream=Slaughter`, and can cancel non-cancelled rows through `POST /api/sales-transactions/<sale_id>/cancel`.
- Local page smoke passed for `/sales/slaughter`.
- Local verification passed on 2026-05-21: focused frontend/sales tests passed at 27 tests.
- Full local unittest suite passed on 2026-05-21 at 192 tests.
- Next deployed test should open `/sales/slaughter`, confirm the page loads active pigs and recent cancelled synthetic transactions, then owner can enter real `S10` when ready.
- 10.2L2 payment/final amount update is implemented locally and not yet deployed.
- New route: `PATCH /api/sales-transactions/<sale_id>/payment`.
- The update route is for `Slaughter` transactions only, refuses cancelled rows, requires `updated_by`, `update_reason`, amount, payment status, and sale status, updates header totals/payment/status, updates the first item amount and optional carcass weight, and appends an audit note.
- The `/sales/slaughter` page now shows `Update Payment` for non-cancelled rows.
- Local missing-config route smoke returned safe `503` with no Supabase write.
- Local verification passed on 2026-05-21: focused sales/frontend tests passed at 23 tests.
- Full local unittest suite passed on 2026-05-21 at 200 tests.
- Next deployed test should update a synthetic non-cancelled transaction before using this for real `S10` payment completion.

Open questions before implementation:

- Should the first deployed write test use synthetic `PIG-TEST-*` IDs only, or should we use real slaughter candidate `S10` after the write/cancel behavior is proven?
- Should `created_by` be required for every write? Recommended: yes.
- Should a transaction be editable after creation, or should correction be cancel-and-recreate only? Recommended: cancel-and-recreate until audit rules are mature.
- Should VAT fields be added before the first real JC Slaghuis transaction, or can the first slice store VAT context in `notes` and add structured VAT fields before dashboard financial reporting?

## Import Rules

Initial rules carried forward from Phase 7.2:

- Exclude test customer name `Charl N`.
- Exclude obvious dry-run/test orders.
- First import should include completed real orders only, to start Supabase with a small clean historical set.
- Exclude draft, pending, approved, rejected, and cancelled orders from the first import even if they have documents/history, unless the owner manually approves a specific exception later.
- Preserve original public IDs.
- Add `source_sheet_row` and `import_batch_id` to imported records.
- Dry-run report must show included rows, excluded rows, and exclusion reason.
- Unlinked test/status-log data should be excluded from the Supabase import if it is not linked to an included main order. Do not clean/delete Sheets rows as part of this migration step.

Do not manually decide row by row during import. The exclusion logic must be documented and repeatable.

## Implementation Sequence

Recommended sequence:

1. Finalize schema fields and indexes in this document.
2. Create SQL migration for empty business tables only.
3. Run SQL migration in Supabase SQL Editor.
4. Add backend schema verification endpoint or script.
5. Build import dry-run script that reads Sheets and reports what would import.
6. Review dry-run report before importing any rows.
7. Import to Supabase in shadow mode only.
8. Compare Supabase read models against current Sheet-backed backend outputs.
9. Move selected reads behind a feature flag only after shadow checks pass.
10. Move writes only after backup, rollback, and operator views are accepted.

## 10.2B Import Dry-Run Plan

Purpose:

- inspect current Google Sheets order/sales rows before any import
- produce repeatable include/exclude decisions
- expose missing links and likely cleanup needs
- write nothing to Supabase

Dry-run script:

- `scripts/order_sales_import_dry_run.py`

Command:

```powershell
.\venv\Scripts\python.exe scripts\order_sales_import_dry_run.py --summary-only
```

Safety rules:

- The script reads Google Sheets only.
- The script does not connect to Supabase.
- The script does not write files by default.
- The script prints JSON to the terminal.
- The script reports `writes_to_supabase = false`.

Current decision rules:

| Data | Include | Exclude |
| --- | --- | --- |
| Orders | Real completed orders with usable order ID | Missing order ID, customer `Charl N`, test markers, any order not `Completed` |
| Order lines | Parent order is included | Missing line ID, missing parent order, parent order excluded |
| Documents | Parent order is included | Missing document ID, missing parent order, parent order excluded |
| Status logs | Parent order is included | Missing log ID, missing parent order, parent order excluded |
| Intakes | Non-test intake linked to an included draft/main order | Missing intake ID, `Charl N`, test marker, missing/excluded linked draft order, or no linked order |
| Intake items | Parent intake is included | Missing item ID, missing/excluded parent intake |
| Pricing | Sale category, weight band, and price are present | Missing category, weight band, or price |

Known limitation:

- This dry-run classifies rows for review. It does not transform rows into final Supabase insert payloads yet.
- Date/number normalization and final field mapping belong to a later import-mapping slice.

Pass condition:

- Local tests pass.
- Dry-run report runs against live Sheets.
- Owner reviews summary counts and link issues.
- No Supabase rows are inserted.

Implementation state:

- Dry-run script prepared: `scripts/order_sales_import_dry_run.py`.
- Local verification passed on 2026-05-21: focused dry-run tests passed at 5 tests and full local unittest suite passed at 143 tests.
- Live summary-only dry-run ran on 2026-05-21 and reported `writes_to_supabase = false`.

Live dry-run summary on 2026-05-21:

| Sheet | Total | Included | Excluded | Main exclusions |
| --- | ---: | ---: | ---: | --- |
| `ORDER_MASTER` | 82 | 26 | 56 | `test_customer_charl_n = 56` |
| `ORDER_LINES` | 171 | 103 | 68 | `parent_order_excluded = 68` |
| `ORDER_INTAKE_STATE` | 73 | 27 | 46 | `test_customer_charl_n = 44`, `test_marker = 2` |
| `ORDER_INTAKE_ITEMS` | 50 | 7 | 43 | `parent_intake_excluded = 43` |
| `ORDER_DOCUMENTS` | 34 | 6 | 28 | `parent_order_excluded = 28` |
| `ORDER_STATUS_LOG` | 330 | 62 | 268 | `missing_parent_order = 157`, `parent_order_excluded = 111` |
| `SALES_PRICING` | 21 | 21 | 0 | none |

Dry-run finding:

- `ORDER_STATUS_LOG` needs a focused review before import mapping. It has 157 rows where `Order_ID` does not match `ORDER_MASTER`, plus 111 rows linked to excluded test orders.
- This may be historical setup/test data, blank/malformed order IDs, or a status-log format mismatch.
- Do not import status logs until the mismatch is understood.
- Owner decision: test data can stay in Sheets, but if it is not linked to an included main order it should be excluded from Supabase import.

Status-log diagnostic:

- Script: `scripts/order_status_log_diagnostic.py`
- Purpose: classify `ORDER_STATUS_LOG` rows as included candidates, missing order ID, missing parent order, or linked to a test parent order.
- Safety: reads `ORDER_MASTER` and `ORDER_STATUS_LOG` only; writes nothing to Sheets or Supabase.
- Local verification passed on 2026-05-21: focused diagnostic/dry-run tests passed at 7 tests and full local unittest suite passed at 145 tests.
- Live diagnostic ran on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`.

Live status-log diagnostic result:

| Classification | Count | Import decision |
| --- | ---: | --- |
| `included_candidate` | 62 | Include in future dry-run/import mapping. |
| `missing_parent_order` | 157 | Exclude unless owner explicitly identifies a specific row/order as business history. |
| `test_parent_order` | 111 | Exclude by default. |
| `missing_order_id` | 0 | No action needed. |

Decision:

- For import mapping, include only `included_candidate` status logs by default.
- Missing-parent and test-parent status logs can stay in Sheets, but should not move to Supabase unless manually approved later.

## 10.2C Import Mapping Dry-Run Payload Shape

Purpose:

- transform included dry-run rows into Supabase-shaped payloads for review
- catch field, date, phone, number, and JSON mapping issues before any insert
- keep the process read-only

Command:

```powershell
.\venv\Scripts\python.exe scripts\order_sales_import_dry_run.py --summary-only --payload-samples 2
```

Safety rules:

- The mapper still reads Google Sheets only.
- The mapper does not connect to Supabase.
- The mapper does not write files by default.
- The mapper prints JSON only.
- The report must keep `writes_to_supabase = false` and `writes_to_sheets = false`.

Payload behavior:

- Included rows are mapped to the seven target table names.
- Excluded rows are not mapped into payload samples.
- `source_sheet_row` and `import_batch_id = DRY_RUN_ONLY` are added for traceability.
- Phone values map to both raw and normalized fields.
- Money values map to numeric values.
- Boolean-like fields map from values such as `Yes`, `true`, or `1`.
- List-like fields map to JSON-style arrays.
- `sales_pricing` receives deterministic dry-run `pricing_id` values and `currency = ZAR`.
- Unlinked intake rows are excluded from this first import boundary unless manually approved later.

Known limitations:

- Date parsing currently uses the existing project date parser and may drop time precision for some Sheet formats.
- `order_lines.pricing_id` is not linked yet; that belongs in a later pricing reconciliation step.
- The dry-run payload is a review shape, not an approved insert script.

Implementation state:

- Payload mapping added to `scripts/order_sales_import_dry_run.py`.
- Owner rule applied: unlinked intake rows are excluded from the first import boundary.
- Local verification passed on 2026-05-21: focused payload/dry-run tests passed at 7 tests and full local unittest suite passed at 147 tests.
- Live payload sample report ran on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`.

Live mapped payload counts on 2026-05-21:

| Target table | Rows mapped | Notes |
| --- | ---: | --- |
| `orders` | 26 | Included non-`Charl N` orders only. |
| `order_lines` | 103 | Linked to included orders. |
| `order_intakes` | 0 | All current included-looking intakes were unlinked; excluded by owner rule. |
| `order_intake_items` | 0 | Parent intakes excluded. |
| `order_documents` | 6 | Linked to included orders. |
| `order_status_logs` | 62 | Only included-candidate logs linked to included orders. |
| `sales_pricing` | 21 | All current pricing rows mapped with deterministic dry-run IDs. |

Owner decision update:

- First actual import should include only completed real orders. This keeps Supabase clean and small at the start.
- Pricing remains importable as reference data.
- Draft/pending/approved/cancelled/rejected history can stay in Sheets and be considered later only if explicitly needed.

Completed-only dry-run result:

- Ran on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`.
- This is the current approved first-import boundary.

| Target table | Rows mapped | Notes |
| --- | ---: | --- |
| `orders` | 3 | Real completed orders only; excludes `Charl N` and all non-completed orders. |
| `order_lines` | 53 | Linked to the 3 included completed orders. |
| `order_intakes` | 0 | No intakes linked to the completed-order import boundary. |
| `order_intake_items` | 0 | Parent intakes excluded. |
| `order_documents` | 0 | Current documents are linked to excluded/non-completed orders. |
| `order_status_logs` | 11 | Linked to the 3 included completed orders. |
| `sales_pricing` | 21 | Reference pricing remains importable. |

Completed-only source summary:

| Sheet | Total | Included | Excluded | Main exclusions |
| --- | ---: | ---: | ---: | --- |
| `ORDER_MASTER` | 82 | 3 | 79 | `test_customer_charl_n = 56`, `not_completed_order = 23` |
| `ORDER_LINES` | 171 | 53 | 118 | `parent_order_excluded = 118` |
| `ORDER_INTAKE_STATE` | 73 | 0 | 73 | `test_customer_charl_n = 44`, `unlinked_intake_without_order = 27`, `test_marker = 2` |
| `ORDER_INTAKE_ITEMS` | 50 | 0 | 50 | `parent_intake_excluded = 50` |
| `ORDER_DOCUMENTS` | 34 | 0 | 34 | `parent_order_excluded = 34` |
| `ORDER_STATUS_LOG` | 330 | 11 | 319 | `parent_order_excluded = 162`, `missing_parent_order = 157` |
| `SALES_PRICING` | 21 | 21 | 0 | none |

## 10.2D Completed-Only Shadow Import Script

Purpose:

- insert the approved completed-order boundary into Supabase as shadow data only
- keep Google Sheets as the live source of truth
- make the import repeatable and idempotent for the same batch
- avoid importing draft, pending, approved, cancelled, rejected, test, or unlinked rows

Script:

- `scripts/order_sales_shadow_import.py`

Plan-only command:

```powershell
.\venv\Scripts\python.exe scripts\order_sales_shadow_import.py --payload-samples 1
```

Apply command, only after explicit approval:

```powershell
.\venv\Scripts\python.exe scripts\order_sales_shadow_import.py --apply
```

Safety rules:

- Default mode is `plan_only`; it writes nothing.
- Apply mode requires `--apply`.
- Apply mode requires `DATABASE_URL`.
- Apply mode writes only to Supabase and never writes to Google Sheets.
- Rows are inserted/upserted under import batch `IMPORT-20260521-COMPLETED-ORDERS-V1`.
- Insert order respects foreign keys: `sales_pricing`, `orders`, `order_lines`, `order_intakes`, `order_intake_items`, `order_documents`, `order_status_logs`.
- The current approved boundary remains 3 completed orders, 53 linked lines, 11 linked status logs, and 21 pricing rows.

Implementation state:

- Shadow import script prepared on 2026-05-21.
- Apply attempt with missing local `DATABASE_URL` failed safely before writing anything.
- First real apply attempt hit a `NotNullViolation`; the transaction rolled back and no Supabase rows were written.
- Import payload timestamp normalization was added before retrying.
- Local verification passed on 2026-05-21: focused shadow-import/dry-run tests passed at 14 tests and full local unittest suite passed at 154 tests after the timestamp fix.
- Live plan-only run passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`.
- Live plan-only payload counts matched the approved completed-only boundary.
- Shadow import `--apply` passed on 2026-05-21.
- Apply result inserted/upserted: 3 orders, 53 order lines, 11 order status logs, and 21 sales pricing rows. Intakes, intake items, and documents remained 0.
- Verification script `scripts/order_sales_shadow_import_verify.py` confirms Supabase row counts for batch `IMPORT-20260521-COMPLETED-ORDERS-V1`.
- No backend order route has been changed to read or write Supabase.

Verified Supabase counts:

| Target table | Rows in batch |
| --- | ---: |
| `orders` | 3 |
| `order_lines` | 53 |
| `order_intakes` | 0 |
| `order_intake_items` | 0 |
| `order_documents` | 0 |
| `order_status_logs` | 11 |
| `sales_pricing` | 21 |

Next step:

- Phase 10.2E should compare Supabase shadow reads against the current Sheet-backed backend outputs before any read cutover is considered.

## 10.2E Shadow Read Comparison

Purpose:

- prove the Supabase shadow batch matches the current Google Sheets source mapping
- keep the app routes unchanged
- identify count, missing-row, extra-row, and selected field mismatches before any cutover

Script:

- `scripts/order_sales_shadow_compare.py`

Command:

```powershell
.\venv\Scripts\python.exe scripts\order_sales_shadow_compare.py
```

Safety rules:

- Reads Google Sheets.
- Reads Supabase.
- Writes nothing to Google Sheets.
- Writes nothing to Supabase.
- Does not change backend route behavior.

Comparison result:

- Ran on 2026-05-21.
- `success = true`
- `status = ok`
- `mismatch_count = 0`

Verified matching tables:

| Target table | Expected | Actual | Mismatches |
| --- | ---: | ---: | ---: |
| `orders` | 3 | 3 | 0 |
| `order_lines` | 53 | 53 | 0 |
| `order_intakes` | 0 | 0 | 0 |
| `order_intake_items` | 0 | 0 | 0 |
| `order_documents` | 0 | 0 | 0 |
| `order_status_logs` | 11 | 11 | 0 |
| `sales_pricing` | 21 | 21 | 0 |

Decision:

- Phase 10.2E is complete for the completed-order shadow batch.
- This does not approve backend read cutover.
- Next phase should plan a read-only Supabase endpoint or service comparison behind an explicit feature boundary.

## 10.2F Read-Only Shadow Endpoint

Purpose:

- expose a controlled backend comparison path for a single imported order
- keep the live `/api/orders/<order_id>` route on Google Sheets
- avoid any app UI or workflow cutover
- make Supabase comparison testable through the Flask app boundary

Endpoint:

```text
GET /api/shadow/orders/<order_id>/compare
```

Safety rules:

- Read-only.
- Reads the current Google Sheets order detail.
- Reads the imported Supabase shadow order detail for batch `IMPORT-20260521-COMPLETED-ORDERS-V1`.
- Writes nothing to Google Sheets.
- Writes nothing to Supabase.
- Does not alter `/api/orders/<order_id>`.
- Does not alter any order create/update/cancel/approval/write path.

Implementation state:

- Service added: `modules/orders/order_shadow_read.py`.
- Route added: `GET /api/shadow/orders/<order_id>/compare`.
- Local verification passed on 2026-05-21: focused shadow route/service tests passed at 32 tests and full local unittest suite passed at 164 tests.
- Local API smoke passed for `ORD-2026-0B29D7`: HTTP 200, `success = true`, `status = ok`, `mismatch_count = 0`, `writes_to_sheets = false`, and `writes_to_supabase = false`.
- Deployed verification passed on 2026-05-21 for `ORD-2026-0B29D7`: HTTP response returned `success = true`, `status = ok`, `mismatch_count = 0`, and read-only flags `writes_to_sheets = false`, `writes_to_supabase = false`.

Not approved:

- No route cutover.
- No UI change.
- No n8n workflow change.
- No Supabase write path for live orders.

Next step:

- Plan the next Supabase slice deliberately. Options are a feature-flagged read model, a broader completed-order import/reimport process, or moving to Phase 10.3 telemetry review.

## 10.2A Recommended First Slice

First implementation slice should not import data yet.

Recommended 10.2A:

- Create empty Supabase business tables for the seven-table boundary.
- Include primary keys, foreign keys, core indexes, and import traceability columns.
- Add a backend/schema verification route or script.
- Do not change existing backend order routes to read or write Supabase.
- Do not import Google Sheets data yet.

Pass condition:

- SQL migration runs successfully.
- Schema verification confirms the seven expected tables exist.
- Existing app tests still pass.
- Current live order system still uses Google Sheets.

Implementation state:

- SQL migration prepared: `supabase/migrations/202605210002_create_order_sales_tables.sql`.
- Backend verification route prepared: `GET /health/database/order-schema`.
- No data import script has been created yet.
- No backend order route has been changed to read or write Supabase.
- Local verification passed on 2026-05-21: focused database tests passed at 9 tests and full local unittest suite passed at 138 tests.
- Deployed verification passed on 2026-05-21: owner ran the SQL migration and `/health/database/order-schema` returned `success = true`, `status = ok`, migration ID `202605210002_create_order_sales_tables`, all seven expected tables found, and no missing tables.

Expected verification response after migration is applied:

```json
{
  "success": true,
  "configured": true,
  "status": "ok",
  "migration_id": "202605210002_create_order_sales_tables",
  "expected_tables": [
    "order_documents",
    "order_intake_items",
    "order_intakes",
    "order_lines",
    "order_status_logs",
    "orders",
    "sales_pricing"
  ],
  "missing_tables": []
}
```

## Open Questions Before 10.2A SQL

1. Should `sales_pricing` start with current prices only, or should we immediately add future effective-date pricing support in the first schema?
2. Should `order_status_logs.status_log_id` be required for imported rows, or should import generate IDs for legacy rows when missing?
3. Should `order_documents` store Google Drive file metadata only, or should it also reserve columns for future Supabase Storage paths?
4. Should `orders.customer_phone` preserve raw phone only, or store both raw and normalized phone from the start?
5. Should import exclude all `Charl N` rows, or only `Charl N` rows created during known test windows?
6. Should the first empty-table migration include SQL comments on columns for Supabase UI readability?

## Recommendation On Open Questions

Suggested defaults:

1. Add effective-date pricing fields now, even if only current prices are imported first.
2. Require `status_log_id` in the Supabase table; generate stable import IDs for legacy rows that do not have one.
3. Store Google Drive fields now and add nullable future storage fields only if clearly named.
4. Store both `customer_phone_raw` and `customer_phone_normalized`.
5. Exclude all `Charl N` rows by default unless the owner explicitly identifies one as real.
6. Add SQL column comments where helpful, but do not overdo comments for every obvious field.

Owner decision:

- Owner accepted the recommended defaults on 2026-05-21.

## Still Not Approved

- Empty order/sales business table migration has been approved, run, and verified for 10.2A only.
- Completed-order shadow import for batch `IMPORT-20260521-COMPLETED-ORDERS-V1` has been approved, applied, and verified only as shadow data.
- Read-only shadow comparison endpoint has been approved and verified only for comparison.
- No live backend order read/write cutover has been approved yet.
- No Google Sheet retirement has been approved yet.
