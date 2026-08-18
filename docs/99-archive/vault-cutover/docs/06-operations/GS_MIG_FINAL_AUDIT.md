# GS-MIG-FINAL Google Sheets Caller Audit

Date: 2026-06-29

Branch: `gs-mig-final-audit-and-closeout`

Mode: final migration closeout audit plus one remaining route-facing read cutover. No production Google Sheets writes, Supabase writes, customer sends, public posts, payments, reservations, lifecycle writes, Phase 3A.6 work, CHARLIE/FRED/ledger work, screenshots, external sources, assets, `.env`, or `.claude` changes were made during this audit.

## 1. Executive Result

Normal app operation is now Supabase-first for the migrated operational domains.

The remaining Google Sheets callers are classified as:

- safe fallback only
- import/export/admin script
- legacy/reference only
- test fixture/mocking support

No remaining caller was found that should stay classified as an active route that must still be migrated before declaring the route cutover complete.

One route-facing gap was closed during this audit: litter lifecycle action validation still read `PIG_MASTER`, `LITTER_OVERVIEW`, `LITTERS`, or `PRODUCT_REGISTER` directly before using Supabase write rails. The new code reads Supabase sheet-shaped pig/litter/product rows first and keeps the legacy Sheets path only as fallback.

## 2. Commands Used

- `git branch --show-current`
- `git status --short --untracked-files=all`
- `git log --oneline --decorate -12 origin/main`
- `git diff --name-only origin/main`
- `git diff --stat origin/main`
- `rg -n "get_all_records\(|get_all_values\(|append_row\(|batch_update_rows_by_id\(|update_row_by_first_column_match\(|ensure_worksheet\(" modules services scripts app.py`
- `rg -n "WEIGHT_LOG|LOCATION_HISTORY|PIG_MASTER|PIG_OVERVIEW|PEN_REGISTER|SALES_STOCK|ORDER_LINES|ORDER_MASTER|ORDER_STATUS_LOG|LITTER|MATING|PIGLETS" modules services scripts app.py`

## 3. Active Route Must Still Be Migrated

None found after this audit branch.

Closed in this branch:

| Area | Previous issue | Fix |
| --- | --- | --- |
| Litter lifecycle action validation | Litter actions used direct `PIG_MASTER`/`LITTER_OVERVIEW`/`LITTERS`/product Sheet reads for candidate validation before Supabase writes. | Added Supabase read helpers for sheet-shaped pig master and litter register rows; routed litter action validation through Supabase-first helpers; kept Sheets fallback. |
| Legacy pen fallback | Sheet fallback pen lookup treated blank `Is_Active` values as inactive, which could hide legacy pen names in fallback reports. | Blank legacy active flags are treated as active; explicit `No`/other values remain inactive. |
| Irrigation explicit sheet inspection | Explicit `spreadsheet_name` calls could still default to Supabase `auto` if a live env was present. | Explicit spreadsheet inspection now defaults to the sheet bridge unless `IRRIGATION_STATUS_SOURCE` is explicitly set. |

## 4. Safe Fallback Only

These modules are route-facing, but normal behavior is Supabase-first. The Google Sheets calls remain fallback paths for `DATABASE_URL` unavailable, Supabase helper unavailable, or controlled Supabase helper failure.

| File | Caller group | Classification | Notes |
| --- | --- | --- | --- |
| `modules/pig_weights/pig_weights_service.py` | Farm dashboard, litter overview/detail, sales stock, allocation, meat planning, pig detail/history, products, pens, weight reports, single farm writes, litter actions, bulk legacy audit | Safe fallback only | Supabase canonical reads/writes are preferred. This branch added Supabase-first full pig/litter rows for litter action validation. Legacy bulk audit Sheet append remains compatibility/export fallback. |
| `modules/pig_weights/mating_service.py` | Breeding options, mating overview, analytics, mating writes, pregnancy status, pen validation, movement logging | Safe fallback only | Supabase read service and mating write service are preferred; Sheets remain fallback when Supabase rails are unavailable/fail. |
| `modules/telemetry/irrigation_service.py` | Irrigation status | Safe fallback only | Default `auto` mode reads Supabase first and falls back to the irrigation sheet only when Supabase has no plan rows or is unavailable. Hardware control remains disabled/read-only. |
| `modules/orders/order_read.py` | Order list/detail/search and rollups | Safe fallback only | Supabase order reads are tried first. `ORDER_*` reads are fallback after Supabase read unavailability/failure. |
| `modules/orders/order_write.py` | Order create/update/line writes | Safe fallback only | Supabase write helpers are preferred when available; Sheets remain legacy fallback. |
| `modules/orders/order_reservation.py` | Reserve/release order lines | Safe fallback only | Supabase order line/order master writes are preferred when available; Sheets remain fallback. |
| `modules/orders/order_lifecycle.py` | Send/approve/reject/cancel/complete order flows | Safe fallback only | Supabase order lifecycle writes are preferred when available; Sheets remain fallback. Customer notification behavior was not changed by this audit. |
| `modules/orders/order_line_sync.py` | Order-line sync from requests | Safe fallback only | PR #38 hardened Supabase-first order/pricing/line helpers with Sheets fallback if helper calls fail. |
| `modules/orders/order_status_log.py` | Status-log append | Safe fallback only | PR #37 made Supabase status-log writes primary and Sheet append fallback if Supabase insert fails. |
| `modules/orders/order_intake_service.py` | Intake state/items update/reset | Safe fallback only | Supabase intake store is preferred; Sheet state/item rows remain fallback. |
| `modules/documents/document_service.py` | Document settings and metadata | Safe fallback only | Supabase `app_settings`/`order_documents` preferred; Sheets fallback remains. |
| `modules/documents/quote_service.py` | Quote order-line lookup | Safe fallback only | Supabase order detail is preferred; `ORDER_LINES` fallback remains. |
| `modules/reports/report_service.py` | Daily order status logs | Safe fallback only | Supabase status-log reads preferred; `ORDER_STATUS_LOG` fallback remains. |
| `modules/sales/sales_transaction_lifecycle.py` | Slaughter/sales pig exit reconciliation | Safe fallback only | Supabase pig lifecycle writes preferred; `PIG_MASTER` fallback remains. |

## 5. Import / Export / Admin Scripts

These are not active app routes. They intentionally read or write Google Sheets for migration tooling, diagnostics, or owner-approved setup/export workflows.

| File | Classification | Notes |
| --- | --- | --- |
| `scripts/google_sheets_farm_import_dry_run.py` | Import/export/admin script | Read-only farm import dry-run source loader. |
| `scripts/google_sheets_farm_import_execute.py` | Import/export/admin script | Controlled import executor; not an app route. |
| `scripts/google_sheets_farm_import_reconcile.py` | Import/export/admin script | Reconciliation report tooling. |
| `scripts/google_sheets_supabase_formula_shadow.py` | Import/export/admin script | Read-only formula shadow comparison. |
| `scripts/order_sales_import_dry_run.py` | Import/export/admin script | Order/sales import dry-run tooling. |
| `scripts/order_sales_live_import.py` | Import/export/admin script | Controlled order/sales import tooling. |
| `scripts/order_status_log_diagnostic.py` | Import/export/admin script | Diagnostic script for imported status logs. |
| `scripts/irrigation_import_dry_run.py` | Import/export/admin script | Read-only irrigation import planning. |
| `scripts/irrigation_daily_sync.py` | Import/export/admin script | Explicit sync script, not a route dependency. |
| `scripts/setup_document_infrastructure.py` | Import/export/admin script | Legacy document-sheet setup helper. |
| `scripts/setup_order_intake_infrastructure.py` | Import/export/admin script | Legacy order-intake sheet setup helper. |

## 6. Legacy / Reference Only

| File | Classification | Notes |
| --- | --- | --- |
| `services/google_sheets_service.py` | Legacy/reference only | Central Google Sheets wrapper retained for fallback/export/admin scripts. Not canonical operational truth. |
| `services/google_drive_service.py` | Legacy/reference only | Google Drive integration reuses service-account constants. This is document storage integration, not farm operational Sheets truth. |
| `modules/orders/order_shadow_read.py` | Legacy/reference only | Shadow comparison wording still references Google Sheets as legacy live/source context. |
| `modules/oom_sakkie/agent_runtime.py` | Legacy/reference only | Mentions Google Sheets in static runtime text; no operational sheet read/write. |

## 7. Tests / Fixtures

Tests intentionally patch or assert Google Sheets helpers for fallback behavior. These are not production dependencies.

Examples:

- `tests/test_pig_weights_litter_service.py`
- `tests/test_pig_weights_bulk_service.py`
- `tests/test_order_service_sync.py`
- `tests/test_order_status_log.py`
- `tests/test_frontend_route_contracts.py`

## 8. Closed During This Audit

Added:

- `farm_supabase_read_service.get_pig_master_rows()`
- `farm_supabase_read_service.get_litter_register_rows()`
- `pig_weights_service._get_pig_master_rows()`
- `pig_weights_service._get_litter_register_rows()`
- `pig_weights_service._get_litter_overview_rows()`

Updated:

- Litter birth reconciliation and stillborn reclassification now use Supabase-first litter overview rows.
- Litter birth-count register validation now uses Supabase-first litter register rows.
- Litter weaning now uses Supabase-first pig rows and current-weight fields before falling back to `WEIGHT_LOG`.
- Litter piglet death, sex count, tag assignment, newborn health, and pig death/removal candidate validation now use Supabase-first pig rows.
- Newborn health product validation now uses `get_products()`, which is Supabase-first.

## 9. Final Classification Summary

| Category | Count / status |
| --- | --- |
| Active route that must still be migrated | 0 |
| Safe fallback only | Present by design |
| Import/export/admin script | Present by design |
| Legacy/reference only | Present by design |
| Test fixtures | Present by design |

## 10. Completion Criteria

Call the Google Sheets to Supabase operational route migration complete only after:

- Focused route/service tests pass.
- Full unit discovery passes or any failures are classified as unrelated/pre-existing with exact evidence.
- GitHub PR checks pass.
- Owner has reviewed the final PR report.

## 11. Test Evidence

Full `unittest discover tests` exceeded the local 10-minute command timeout without failure output, so the same suite was run by module chunks. All chunked module runs passed.

Additional checks:

- `node --check static/js/bulkWeights.js`
- `node --check tests/bulk_weights_draft_recovery_node.js`
- `node tests/bulk_weights_draft_recovery_node.js`

Focused and chunked Python coverage included:

- farm Supabase read/write cutover
- pig weights bulk, dashboard, litter, report, duplicate, and utility services
- frontend route contracts
- order read/write/lifecycle/reservation/sync/status-log routes and services
- document/quote Supabase reads
- order/sales import and shadow tooling
- irrigation import/status/telemetry
- mating/breeding routes and services
- sales transaction lifecycle/routes/read/update/cancel/create
- Oom Sakkie routes/services
- SAM runtime/command-state/stress/context groups
- workflow, power, weather, telemetry rollup groups

## 12. Remaining Non-Blocking Follow-Ups

- Decide later whether to remove legacy Google Sheets fallback code after an owner-approved stability window.
- Decide later whether Google Sheets should receive export/sync snapshots for reporting only.
- Keep import/admin scripts, but do not run write/apply modes without explicit owner approval.
- Keep the 9 conflicting-weight groups on the owner/admin review list until resolved.
