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
