# Supabase Order Schema Plan

## Purpose

Phase 10.2 planning document.

This document turns the Phase 7.2 database scaling draft into a first implementation boundary for orders/sales data in Supabase/Postgres.

This is still planning. Do not create business tables until this plan is accepted.

## Current Status

- Phase 10.1A database connection is deployed and verified.
- Phase 10.1B baseline migration is deployed and verified.
- Supabase currently has only the internal `app_private.migration_log` baseline table from this project.
- No order, pig, customer, document, pricing, telemetry, or business tables have been created.
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

## Import Rules

Initial rules carried forward from Phase 7.2:

- Exclude test customer name `Charl N`.
- Exclude obvious dry-run/test orders.
- Import real active, pending, approved, completed, and useful historical orders.
- Import real cancelled orders only when they have business/audit value, such as documents, payment notes, delivery notes, or meaningful customer history.
- Preserve original public IDs.
- Add `source_sheet_row` and `import_batch_id` to imported records.
- Dry-run report must show included rows, excluded rows, and exclusion reason.

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

## Not Yet Approved

- Empty order/sales business table migration has been approved for 10.2A only.
- No import script has been approved yet.
- No backend read/write cutover has been approved yet.
- No Google Sheet retirement has been approved yet.
