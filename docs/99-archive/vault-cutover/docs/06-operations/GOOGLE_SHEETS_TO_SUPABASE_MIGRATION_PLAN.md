# Google Sheets To Supabase Migration Plan

Planning date: 2026-06-29

Mode: report-only. No code changes, migrations, Google Sheets writes, Supabase writes, customer sends, public posts, payments, reservations, lifecycle writes, or production behavior changes were made for this plan.

## 1. Executive Decision

Recommendation: move the operational source of truth from Google Sheets to Supabase in phases.

Supabase should become the canonical operational database for pig master data, weights, location history, litters, breeding, medical/hold state, stock readiness, orders, pricing, telemetry, and audit trails. Google Sheets should remain as legacy reference, backup/export layer, and optional reporting view, not as the critical app read/write path.

Do not attempt a one-shot cutover. The current app still reads or writes many Google Sheets directly. A safe migration needs read-only inventory, dry-run import, reconciliation, shadow reads, route-by-route cutover, and owner sign-off at every production write boundary.

Immediate P0 decision: stop treating Google Sheets as the durable first write for weekly bulk weights. Bulk weights and pen movements should become Supabase canonical events, with Google Sheets as downstream compatibility/export only.

## 2. Current Google Sheets Dependency Map

Primary dependency layer:

| Area | Files | Sheets | Read/write | Risk | Proposed replacement |
| --- | --- | --- | --- | --- | --- |
| Google Sheets access wrapper | `services/google_sheets_service.py` | all configured sheets | read/write helper layer | retries only quota errors; synchronous app calls; app exceptions can surface as HTML/timeouts | replace operational callers with Supabase repository/services; keep wrapper for export/legacy reads only |
| Pig operations and dashboards | `modules/pig_weights/pig_weights_service.py`, `modules/pig_weights/pig_weights_routes.py`, `app.py`, `templates/*`, `static/js/*` | `PIG_MASTER`, `PIG_OVERVIEW`, `WEIGHT_LOG`, `LOCATION_HISTORY`, `PEN_REGISTER`, `PRODUCT_REGISTER`, `MEDICAL_LOG`, `LITTERS`, `LITTER_OVERVIEW`, `SALES_AVAILABILITY`, `SALES_STOCK_SUMMARY`, `SALES_STOCK_TOTALS` | heavy read/write | highest operational risk; weekly weights already failed repeatedly | canonical pig, pen, weight, location, medical, litter, and derived-state tables/views |
| Bulk weight rail | `modules/pig_weights/bulk_weight_batch_service.py`, `modules/pig_weights/pig_weights_routes.py`, `static/js/bulkWeights.js` | downstream currently still reaches `WEIGHT_LOG` and `LOCATION_HISTORY` | write | high P0 risk if Sheets remains first durable record | Supabase batch plus canonical event write, chunked downstream Sheets sync |
| Pig allocation/readiness | `modules/pig_allocation/*`, pig weight services | `PIG_OVERVIEW`, `SALES_AVAILABILITY`, `WEIGHT_LOG`, status/purpose fields | read | formula/stale-data risk | Supabase current-state/readiness views |
| Meat planning and sales dashboard | `modules/pig_weights/pig_weights_service.py`, `modules/sales/*`, dashboard templates/static | `SALES_STOCK_SUMMARY`, `SALES_STOCK_TOTALS`, `SALES_AVAILABILITY`, `SALES_PRICING` | read | formula mismatch and hidden eligibility gate risk | Supabase stock readiness and valuation views using current price tables |
| Breeding/litters | `modules/pig_weights/mating_service.py`, litter functions | `MATING_LOG`, `MATING_OVERVIEW`, `LITTERS`, `LITTER_OVERVIEW`, `PIG_OVERVIEW`, `PEN_REGISTER`, `LOCATION_HISTORY` | read/write | medium/high, depends on formula sheets | canonical litter and mating event tables plus derived views |
| Orders and reservations | `modules/orders/*`, `modules/documents/*`, `modules/reports/*` | `ORDER_MASTER`, `ORDER_LINES`, `ORDER_OVERVIEW`, `ORDER_STATUS_LOG`, `ORDER_DOCUMENTS`, `ORDER_INTAKE_STATE`, `ORDER_INTAKE_ITEMS`, `SALES_AVAILABILITY`, `SALES_PRICING`, `PIG_MASTER` | read/write | medium/high; Supabase order tables exist but app still has Sheets callers | finish order-domain cutover to existing Supabase tables, then remove Sheets write path |
| Sales transaction lifecycle | `modules/sales/sales_transaction_lifecycle.py` | `PIG_MASTER` | read/write | changes pig status/on-farm fields through Sheets | replace with Supabase pig status/sale lifecycle events |
| Telemetry/irrigation import | `modules/telemetry/irrigation_service.py`, `scripts/irrigation_*` | separate spreadsheet | read | lower operational risk for pig tracker, but still Sheets-backed | keep separate migration track; Supabase telemetry tables already exist |
| Google Drive documents | `services/google_drive_service.py`, `modules/documents/*` | service account shared with Sheets | file/doc access | not part of core pig data migration | keep as separate document storage decision |

Important direct dependency searches covered `google`, `sheet`, `gspread`, `worksheet`, `spreadsheet`, `WEIGHT_LOG`, `LOCATION_HISTORY`, `SALES_STOCK`, `allocation`, `meat-planning`, `bulk-weight`, `bulkWeights`, `append_row`, `batch_update`, `get_all_records`, and `service_account`.

## 3. Google Sheets Tab Inventory

Read-only live inventory succeeded using the existing service account. No sheet writes were made.

| Sheet | Live non-empty rows | Type | Purpose | Migration action |
| --- | ---: | --- | --- | --- |
| `PIG_MASTER` | 218 | master | pig identity/status/source fields | migrate to `pigs`; preserve source row and import batch |
| `PIG_OVERVIEW` | 218 | formula view | current pig state, weights, pen, sale readiness, attention flags | replace with Supabase view/materialized view |
| `WEIGHT_LOG` | 1242 | log/history | pig weight history | migrate to `pig_weight_events` |
| `LOCATION_HISTORY` | 186 | log/history | pig movement/pen history | migrate to `pig_location_events` |
| `PEN_REGISTER` | 21 | register | pen names/types/capacity | migrate to `pens` |
| `MEDICAL_LOG` | 262 | log/history | treatments and withdrawal | migrate to `pig_medical_events` or `pig_hold_events` |
| `LITTERS` | 18 | master/log | litter source records | migrate to `litters` |
| `LITTER_OVERVIEW` | 18 | formula view | litter counts/status/weights | replace with Supabase view/service |
| `MATING_LOG` | 16 | event log | breeding transactions | migrate to `mating_events` |
| `MATING_OVERVIEW` | 16 | formula view | breeding status and expected dates | replace with Supabase view/service |
| `ORDER_MASTER` | 85 | master | order headers | Supabase `orders` exists; reconcile and cut over callers |
| `ORDER_LINES` | 172 | master/detail | order lines and reservation state | Supabase `order_lines` exists; reconcile and cut over callers |
| `ORDER_STATUS_LOG` | 333 | audit log | order status history | Supabase `order_status_logs` exists; reconcile and cut over callers |
| `ORDER_OVERVIEW` | 85 | formula view | order display/reporting | replace with Supabase view/service |
| `SALES_AVAILABILITY` | 22 | formula gate | sale eligibility source for AI/order matching | replace with Supabase stock readiness view |
| `SALES_STOCK_SUMMARY` | 22 | formula display | grouped sales stock | replace with Supabase summary view |
| `SALES_STOCK_TOTALS` | 7 | formula display | category totals | replace with Supabase summary view |
| `SALES_PRICING` | 22 | reference | pricing source | Supabase `sales_pricing` exists; reconcile and cut over |
| `PRODUCT_REGISTER` | 4 | register | medical product defaults | migrate to product/settings table |
| `SYSTEM_SETTINGS` | 19 | register | document/config settings | migrate to app settings table |

Sheet docs also define `ORDER_DOCUMENTS`, `ORDER_INTAKE_STATE`, `ORDER_INTAKE_ITEMS`, and `USERS`; these must be included in a full import even if not in the compact live inventory above.

## 4. Formula / Calculated Sheet Inventory

The documented formula chain is:

- `PIG_MASTER`, `WEIGHT_LOG`, `MEDICAL_LOG`, `LOCATION_HISTORY`, and `ORDER_LINES` feed `PIG_OVERVIEW`.
- `PIG_OVERVIEW` feeds `SALES_AVAILABILITY`.
- `SALES_AVAILABILITY` plus `SALES_PRICING` feed `SALES_STOCK_DETAIL`, `SALES_STOCK_SUMMARY`, and `SALES_STOCK_TOTALS`.
- `ORDER_MASTER`, `ORDER_LINES`, and `ORDER_STATUS_LOG` feed `ORDER_OVERVIEW`.
- `LITTERS`, `PIG_MASTER`, and `PIG_OVERVIEW` feed `LITTER_OVERVIEW`.
- `MATING_LOG`, `LITTERS`, and related pig data feed `MATING_OVERVIEW`.

Replacement plan:

| Formula group | Current purpose | Supabase replacement | Test requirement |
| --- | --- | --- | --- |
| `PIG_OVERVIEW` | current pig state, latest/previous weight, gain, pen, withdrawal, reservation, sale readiness | `pig_current_state` view or materialized view backed by event tables | row-by-row comparison against Sheets for all active pigs |
| `SALES_AVAILABILITY` | sale eligibility gate | `sales_stock_readiness` view/service | verify sale-ready, excluded, reserved, withdrawal, and missing-weight cases |
| `SALES_STOCK_DETAIL/SUMMARY/TOTALS` | sales stock display and totals | Supabase detail/summary/totals views | totals reconciliation; newborn/info rows separate from sale-ready rows |
| `ORDER_OVERVIEW` | order display/reporting | Supabase order read service/view | compare order counts, active/cancelled line counts, statuses |
| `LITTER_OVERVIEW` | litter counts, age, sex, weights, attention flags | `litter_overview` view/service | compare litter counts and weight averages |
| `MATING_OVERVIEW` | breeding status and due dates | `mating_overview` view/service | compare expected dates, outcomes, overdue flags |

Formula outputs must not become manual write targets in Supabase. They should be views, materialized summaries, or backend calculations with repeatable tests.

## 5. Current Supabase Schema Map

Read-only Supabase schema inspection succeeded. No database writes were made.

Public schema has 75 tables. Existing relevant coverage:

- Order domain: `orders`, `order_lines`, `order_intakes`, `order_intake_items`, `order_documents`, `order_status_logs`, `sales_pricing`.
- Sales transactions: `sales_transactions`, `sales_transaction_items`.
- SAM/meat/Beacon/Oom Sakkie domains: `oom_sakkie_sales_leads`, `oom_sakkie_sales_lead_events`, `oom_sakkie_meat_price_book_entries`, meat reservation/deposit/fulfillment/instruction tables, Beacon media/campaign/post tables, Oom Sakkie trace/dispatch/patch tables.
- Telemetry/irrigation: telemetry and irrigation tables exist.
- Bulk staging/audit: `bulk_weight_batches`, `bulk_weight_batch_rows`.

Important missing canonical farm tables:

- `pigs`
- `pens`
- `pig_weight_events`
- `pig_location_events`
- `pig_current_state`
- `litters`
- `mating_events`
- `medical_events`

Conclusion: Supabase already supports several newer operational modules, but it is not yet the canonical pig-tracking database. The bulk batch rail stages rows, but it does not by itself replace `PIG_MASTER`, `WEIGHT_LOG`, `LOCATION_HISTORY`, or the formula overview chain.

## 6. Data Domain Mapping

| Domain | Current Google Sheets source | Current Supabase coverage | Target |
| --- | --- | --- | --- |
| Pig identity/status | `PIG_MASTER` | missing | `pigs`, `pig_status_events` |
| Pen register | `PEN_REGISTER` | missing | `pens` |
| Weight history | `WEIGHT_LOG` | batch staging only | `pig_weight_events` |
| Movement history | `LOCATION_HISTORY` | batch staging only | `pig_location_events` |
| Current pig state | `PIG_OVERVIEW` formula | missing | `pig_current_state` view/materialized view |
| Medical/withdrawal | `MEDICAL_LOG`, formula fields | missing | `pig_medical_events`, `pig_hold_events`, derived withdrawal state |
| Litters | `LITTERS`, `LITTER_OVERVIEW` | missing | `litters`, `litter_pig_links`, `litter_overview` |
| Breeding | `MATING_LOG`, `MATING_OVERVIEW` | missing | `mating_events`, `mating_overview` |
| Orders | `ORDER_MASTER`, `ORDER_LINES`, `ORDER_STATUS_LOG`, `ORDER_OVERVIEW` | existing tables | reconcile and cut over callers |
| Pricing | `SALES_PRICING`, meat price book | existing `sales_pricing` and meat price book tables | unify price source by route/domain |
| Sales readiness | `SALES_AVAILABILITY`, `SALES_STOCK_*` | partially in services, no canonical farm view | Supabase readiness/stock/value views |
| Bulk weekly weights | browser draft -> batch staging -> Sheets | `bulk_weight_batches`, `bulk_weight_batch_rows` | Supabase canonical event write first, Sheets downstream |
| Telemetry/irrigation | separate Sheets/imports | existing telemetry/irrigation tables | keep separate track; not blocker for pig data cutover |

## 7. Proposed Canonical Supabase Model

Use existing tables where they already exist and pass reconciliation. Add new tables only where needed.

- `pigs`: canonical pig identity and slowly changing master fields. Include `pig_id`, `tag_number`, `pig_name`, `status`, `on_farm`, `animal_type`, `sex`, `date_of_birth`, breed/marking fields, `source_sheet_row`, `import_batch_id`, timestamps.
- `pens`: canonical pen/location register with `pen_id`, `pen_name`, `pen_type`, `capacity`, `is_active`, notes, source/import metadata.
- `pig_weight_events`: append-only canonical weights with `weight_event_id`, `pig_id`, `weight_date`, `weight_kg`, weighed-by/source/batch metadata, and idempotency constraints.
- `pig_location_events`: append-only canonical pen movements with `move_event_id`, `pig_id`, `move_date`, `from_pen_id`, `to_pen_id`, reason/source/batch metadata, and duplicate prevention.
- `pig_medical_events`: treatments, withdrawals, holds, follow-up requirements, and source/import metadata.
- `litters` and `mating_events`: canonical breeding and litter inputs replacing `LITTERS` and `MATING_LOG`.
- `pig_current_state`: deterministic current-state view/materialized view replacing `PIG_OVERVIEW`.
- `sales_stock_readiness`, `sales_stock_detail`, `sales_stock_summary`, `sales_stock_totals`, `stock_valuation_view`, `slow_grower_review_view`, and `pen_occupancy_view`: formula replacements.
- `app_settings`: meat window, abattoir window, dashboard settings, document settings.
- `farm_audit_events`: owner-approved purpose/status/lifecycle changes.

Keep `bulk_weight_batches` and `bulk_weight_batch_rows`, but link row results to canonical weight/location event ids after processing.

RLS/access posture: owner/admin server routes use backend-controlled access. Public/browser direct access should not be broad. RLS must be explicit per table before any client-side access is considered.

## 8. Bulk Weights / Pen Movements Recommendation

Recommendation: Option B, Supabase canonical weights/movements now, Sheets downstream/export only.

Reasoning:

- Repeated live owner tests failed on large weekly batches through Google Sheets/Render synchronous upload.
- The app has already needed multiple draft recovery, JSON-safety, durable batch, staged-batch recovery, and one-button flow patches.
- Current live risk is not only UI confusion; it is that Google Sheets remains too close to the critical write path.
- The new bulk batch tables make staging safer, but final durable farm truth still needs canonical `pig_weight_events` and `pig_location_events`.

Near-term P0 target:

1. Browser draft remains durable.
2. Batch rows are staged in Supabase.
3. Processing writes canonical Supabase weight/location events first.
4. Google Sheets sync/export runs downstream in chunks.
5. Sheets sync failure marks export status but does not lose the operational event.
6. Retry is idempotent and row-level.

Do not keep patching the Sheets-first path as the long-term fix.

## 9. Formula Replacement Strategy

| Logic | Supabase strategy | Migration phase |
| --- | --- | --- |
| Latest weight per pig | SQL view over `pig_weight_events` using latest `weight_date` and `created_at` tie-break | GS-MIG-3 |
| Previous weight and gain | SQL view or backend service using ranked weight events | GS-MIG-4 |
| Latest pen/current location | SQL view over `pig_location_events` plus initial master pen fallback | GS-MIG-3/4 |
| Withdrawal clear | view/service over `pig_medical_events` and current date | GS-MIG-4 |
| Sale readiness | `sales_stock_readiness` view using purpose/status/weight/reservation/health/settings | GS-MIG-5 |
| Sales stock summaries | views/materialized summaries over readiness and pricing | GS-MIG-5 |
| Stock valuation | backend/view over readiness groups, latest reliable weight, current configured price | GS-MIG-5 |
| Pen occupancy | view over latest location by pig and active pig filters | GS-MIG-4 |
| Litter overview | view/service over litters, pigs, weights | GS-MIG-4 |
| Mating overview | view/service over mating events and litters | GS-MIG-4 |
| Order overview | Supabase order read service/view | GS-MIG-2/4 |

## 10. Backfill And Reconciliation Strategy

Safe migration sequence:

1. Export full Google Sheets workbook before migration.
2. Create read-only import dry-run tooling.
3. Inventory row counts per sheet and compare against live metadata.
4. Normalize dates with explicit timezone/date-only rules.
5. Normalize IDs, especially `Pig_ID`, `Pen_ID`, `Order_ID`, `Weight_Log_ID`, `Move_Log_ID`.
6. Map pen ID vs pen name using `PEN_REGISTER`; fail rows with unknown pen ids into review, not silent defaults.
7. Validate weight units as kilograms and reject impossible values into review.
8. Detect duplicate weights by pig/date/value/source row.
9. Detect duplicate movements by pig/date/from/to/reason/source row.
10. Backfill into staging tables first if practical.
11. Generate reconciliation report before canonical insert.
12. Insert canonical tables only after owner approval.
13. Run formula equivalence reports comparing Sheets outputs to Supabase outputs.
14. Keep rollback: disable Supabase-read feature flags and fall back to Sheets until route cutover is approved.

Reconciliation outputs must include sheet row counts, imported row counts, rejected row counts, duplicate row counts, hash/checksum per source sheet, sample mismatches, and route-level output comparison.

## 11. App Cutover Strategy

### Cutover A: Read-only mirror

Supabase receives imported copy. App still reads Sheets. Compare outputs in reports only.

### Cutover B: Dual-read verification

App services can read Supabase in shadow mode and log/report discrepancies. Owner sees no behavior change.

Pages for comparison: `/bulk-weights`, `/pig-weights`, `/pig/<id>`, `/pig-allocation`, `/sales-dashboard`, and `/meat-planning`.

### Cutover C: Supabase read for selected pages

Suggested order: `/pig/<id>`, `/pig-allocation`, `/sales-dashboard`, `/meat-planning`, then `/pig-weights` overview.

### Cutover D: Supabase write for selected workflows

Start with bulk weights and pen movements. Later add purpose/lifecycle writes only with owner approval and audit.

### Cutover E: Google Sheets export/sync

Sheets becomes export/reporting layer. Failure to sync no longer blocks app operations.

## 12. Google Sheets Future Role

Future role:

- legacy reference
- owner-readable backup/export
- optional reporting view
- emergency reconciliation source during migration

Not future role:

- critical app write path
- critical app read path for live dashboards
- formula-only operational brain
- hidden reservation/availability authority

Keep `docs/03-google-sheets/` as legacy reference until the migration is complete, then add clear legacy status by owner-approved phase.

## 13. Risk Register

| Risk | Impact | Mitigation | Test/verification |
| --- | --- | --- | --- |
| Data loss during import | high | full export, dry-run, staging tables, no destructive migration | row counts, checksums, rejected row report |
| Duplicate weights | high | idempotency keys and duplicate detection | same pig/date duplicate tests |
| Duplicate movements | high | movement idempotency rules | same pig/date/from/to duplicate tests |
| Formula mismatch | high | formula equivalence reports before cutover | Sheets vs Supabase comparison for all active pigs |
| Pen ID/name mismatch | medium/high | strict `PEN_REGISTER` mapping | unknown pen review rows |
| Dashboard totals change unexpectedly | high | side-by-side dashboard reconciliation | totals and category comparisons |
| Google Sheets users edit old source during migration | medium | cutover freeze window or import timestamp policy | changed-row detection after export |
| App routes still read Sheets | high | dependency search and feature flags | CI grep gate for migrated routes |
| Performance issues | medium | indexes, materialized summaries where needed | 116 active pig load and dashboard performance tests |
| RLS/auth mistakes | high | owner/admin backend routes only until policy reviewed | RLS tests and route access tests |
| Rollback confusion | medium | feature flags and documented cutover status | rollback drills per route |
| Bulk upload still relies on downstream Sheets | high | canonical Supabase event first; Sheets sync after | simulated Sheets failure after canonical write |

## 14. Testing Strategy

Required test categories:

- schema/migration tests
- import/backfill dry-run tests
- formula equivalence tests
- route/service tests
- UI smoke tests
- bulk upload pressure tests
- idempotency tests
- dashboard total reconciliation tests
- old Sheets vs new Supabase comparison tests
- rollback tests

Must include:

- 73-row bulk weight plus pen movement scenario
- 116 active pigs page load
- duplicate location history prevention
- same pig/same day/same pen movement duplicate prevention
- same pig/same date weight duplicate prevention
- weight and movement in the same row
- stale/missing weights
- pen ID vs pen name
- sales stock and meat readiness calculations
- reserved/sold/dead/hold exclusion rules
- formula comparison for `PIG_OVERVIEW`, `SALES_AVAILABILITY`, and `SALES_STOCK_*`

## 15. Proposed Implementation Phases

### GS-MIG-0: Discovery and migration plan

This report. Documentation only.

### GS-MIG-1: Supabase canonical schema and dry-run import tools

Add schema design and read-only import/dry-run scripts. No app cutover. Migration approval required.

### GS-MIG-2: Backfill dry-run and reconciliation report

Export Sheets, run dry-run import, produce row count/hash/mismatch report. No app cutover.

### GS-MIG-3: Bulk weights and pen movements write to Supabase canonical events

Make weekly weights and movements durable in Supabase first. Sheets becomes downstream sync/export.

### GS-MIG-4: Pig detail, allocation, and dashboard reads switch to Supabase

Route-by-route read cutover from Sheets formulas to Supabase views/services.

### GS-MIG-5: Sales dashboard and meat planning formulas replaced

Replace `SALES_AVAILABILITY` and `SALES_STOCK_*` formula dependency.

### GS-MIG-6: Sheets export/sync and legacy mode

Keep Sheets available as export/reporting layer.

### GS-MIG-7: Clean up old Sheets dependencies

Remove or quarantine operational Sheets reads/writes after owner verification. Do not delete sheet data.

## 16. Owner Decisions Needed

1. Confirm Supabase as canonical operational truth for core farm data.
2. Confirm Google Sheets future role: export/reporting only, not app-critical.
3. Approve whether GS-MIG-1 should include canonical pig/pen/weight/location/litter/mating/medical tables.
4. Decide if order-domain Sheets migration should happen in the same migration program or after pig operations are stable.
5. Decide whether manual edits in Google Sheets should freeze during backfill/cutover windows.
6. Decide exact treatment of historical duplicate weights and movements: import all with flags, or dedupe into canonical events with review log.
7. Decide whether existing Google Sheets formulas must be replicated exactly first, or whether known formula issues can be corrected during Supabase replacement.
8. Approve RLS/access posture for owner/admin operational tables.

## 17. Confidence Scores By Area

| Area | Confidence | Reason |
| --- | ---: | --- |
| Current code dependency map | 94% | broad `rg` found direct Sheets callers across pig, orders, documents, sales lifecycle, telemetry/scripts |
| Google Sheets tab inventory | 96% | live read-only metadata and existing `docs/03-google-sheets` agree on core tabs |
| Current Supabase schema map | 95% | read-only schema inspection confirmed 75 tables and missing canonical farm tables |
| Bulk weights recommendation | 97% | repeated live failures prove Sheets-first large-batch write is not reliable enough |
| Formula replacement design | 86% | formula chains are documented, but exact formula equivalence needs executable comparison tests |
| Backfill strategy | 92% | approach is standard and low-risk if staged/dry-run first |
| Full app cutover estimate | 84% | scope is broad and many routes still directly call Sheets |

## 18. GO/NO-GO Recommendation

GO for GS-MIG-1 planning/build proposal: design additive canonical Supabase schema and read-only/dry-run import tooling.

NO-GO for immediate full production cutover.

NO-GO for deleting, editing, or treating Google Sheets as retired.

NO-GO for more bulk-weight Sheets-first patching as the long-term path.

Recommended next approved phase:

GS-MIG-1: canonical schema proposal plus dry-run import tooling. Keep it behind explicit owner approval, with no app cutover until reconciliation proves row counts, duplicates, formula outputs, and route outputs are trustworthy.
