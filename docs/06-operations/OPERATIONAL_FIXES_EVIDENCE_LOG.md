# Operational Fixes Evidence Log

## P0 Bulk Upload HTML/JSON Failure - 2026-06-28

Mode: emergency JSON-safety and upload-pipeline hardening. No production Google Sheets write, Supabase write, migration, customer send, public post, payment/deposit change, reservation change, stock/lifecycle write, screenshot, external source, asset, `.env`, or `.claude` change was made.

Owner live failure:

- Owner entered 73 bulk-weight entries.
- About 21 rows included pen changes.
- Upload failed with `Unexpected token '<', "<html> <"... is not valid JSON`.
- Batch Review showed 73 expected, 0 processed, 43 skipped, 0 blocked, 0 failed.
- Draft recovery appears to have protected the browser draft, but the upload pipeline returned HTML instead of structured JSON.

Root cause class found in code:

- Upload endpoint is `POST /api/pig-weights/weights-batch`.
- Preflight endpoint is `POST /api/pig-weights/weights-batch/preflight`.
- Both routes returned JSON only after service functions returned normally.
- If a service, Google Sheets, audit, validation, or other app-controlled exception escaped the service, Flask could return an HTML error page.
- The frontend called `response.json()` directly, so an HTML Flask/Render error produced the raw `Unexpected token '<'` parser error.
- A Render/platform timeout can still return HTML outside Flask control; the frontend must handle that safely, and durable Supabase-first processing is needed if synchronous Sheets remains unreliable.

Batch count explanation:

- The review count was overloaded. It did not clearly separate visible rows, actionable rows, weight rows, movement-only rows, skipped blank/no-change rows, blocked rows, and failed rows.
- A 73-row batch with about 21 pen changes and 43 blank/no-change rows implies roughly 30 actionable rows. The new pressure test models 9 weight rows + 21 movement-only rows + 43 skipped rows.

P0 fix direction:

- Frontend detects non-JSON or invalid JSON responses before parsing.
- Non-JSON response becomes a structured failure object with endpoint, HTTP status, content type, response preview, and `Server returned non-JSON response... Your draft is still saved`.
- Upload/preflight failure still renders Batch Review and keeps localStorage intact.
- Batch Review now shows visible, actionable, weight rows, pen changes, processed, skipped, blocked, and failed counts.
- Bulk routes wrap app-controlled exceptions and return JSON envelopes instead of Flask HTML.
- Bulk service audit failures degrade inside the result so processed counts are preserved.

Pressure-test coverage added:

- Node draft-recovery harness covers HTML non-JSON response and invalid JSON response.
- Backend route tests prove upload/preflight service exceptions return JSON with no Google Sheets/Supabase write flags.
- Backend pressure test covers 73 submitted rows, 21 pen changes, 43 skipped blank/no-change rows, and explainable counts.
- Backend test covers audit exception after row processing as partial JSON summary instead of route-level crash.

Durable rail decision:

- This branch is an emergency hybrid: app-controlled JSON errors plus draft-safe frontend behavior.
- If owner/live/staged tests still show Render timeout HTML or unreliable synchronous Sheets behavior for large batches, the next P0 should be a Supabase-first durable batch rail with stored batch operation, stored row records, chunked processing, idempotent retries, downstream Sheets sync, and UI operation status.

Owner retest gate:

- The owner should not manually retype or retest large 71/73-row batches until this branch is reviewed, merged, deployed, and automated 73-row + pen-change/non-JSON pressure tests pass.

## P0 Bulk Weight Live Failure - 2026-06-28

Mode: emergency data-loss fix. No production Google Sheets write, Supabase write, migration, customer send, public post, payment/deposit change, reservation change, stock/lifecycle write, screenshot, external source, asset, `.env`, or `.claude` change was made.

Owner live failure:

- Owner entered 71 bulk-weight rows.
- 60 rows were recorded in the draft/session.
- Owner pressed Save Draft, then Upload Batch.
- Page returned a vague "Something went wrong" style error.
- Owner refreshed the page and all entered rows were gone.
- This is classified as a P0 data-loss bug.

Root cause found in code:

- The backend bulk service already had row-level partial-failure information after OP-BUILD-2.
- The frontend `renderReview()` function referenced `failedRows` and `rowResults` without defining them.
- When upload/preflight returned a partial or failed payload, that renderer could throw a JavaScript exception.
- The thrown exception fell into the generic upload catch path, producing the vague error message and hiding useful server details.
- Browser draft storage existed, but Save Draft/autosave/recovery behavior was not strong enough around upload failure, partial success, and refresh.

P0 fix direction:

- Autosave bulk-weight drafts to versioned localStorage after edits.
- Save Draft writes a durable browser draft with draft id, timestamp, expected row count, selected pen context, validation status, and all entered rows.
- Page load shows a recovered unsent-draft banner with restore/discard controls.
- Page load can recover the latest unsent draft even if its weight date differs from today's default date.
- Upload preflight/upload persists the draft before network calls.
- Failed or partial upload keeps all rows and localStorage draft intact.
- Only a complete confirmed success can clear the draft.
- Add Download Draft so the owner can export the entered rows before retrying.
- Backend/API responses now include explicit `ok` and `error` fields around validation, partial failure, and no-ready-rows cases.

Pressure-test coverage added:

- Node draft recovery harness proves Save Draft writes durable localStorage.
- Node harness proves reload recovery restores saved rows.
- Node harness proves a past-date draft is recovered after refresh instead of being hidden by today's default date.
- Node harness proves partial upload failure does not clear localStorage.
- Node harness proves complete confirmed upload may clear localStorage.
- Bulk service unit test covers 71 rows with simulated failure after 60 and asserts partial failure, row-level failures, and no silent partial success.

Owner retest gate:

- The owner should not manually retype the 71-row scenario until this P0 branch is reviewed, merged, deployed, and the local pressure tests pass.
## P0 Staged Batch Auto-Process - 2026-06-29

Mode: P0 live usability/reliability fix. Read-only inspection was performed on staged batch `2241aeab-4f40-4797-882d-1588a17abbd0`. No production batch processing, data writes, migration, customer send, public post, payment/deposit change, reservation change, unrelated lifecycle/purpose write, Phase 3A.6, CHARLIE/FRED/ledger work, screenshot, external source, asset, `.env`, or `.claude` change was made during inspection.

Owner live finding:

- Page showed 116 visible rows and 73 entered weights.
- UI said `No actionable rows - draft kept` while also showing Upload Progress with 42 remaining rows.
- Existing staged batch id: `2241aeab-4f40-4797-882d-1588a17abbd0`.

Read-only batch inspection:

- Batch status: `staged`.
- Batch counts: 116 visible, 42 actionable/processable, 73 weight rows, 28 movement rows, 43 skipped, 31 duplicates, 0 success, 0 failed.
- Row statuses: 42 `staged`, 31 `duplicate`, 43 `skipped`.
- Staged action types: 41 weight rows and 1 duplicate-weight-with-movement row.

Root cause:

- The browser checked `counts.actionable_count`, but the durable endpoint returns `counts.actionable_row_count`.
- That made the upload path think no rows were actionable after staging, even though `remaining_count` was 42.
- Existing saved `batch_id` was restored but not status-checked on page load, so the owner was not guided to Continue Upload.

Fix direction:

- Read both legacy and durable count keys.
- Fetch saved batch status on page load when a draft has `batch_id`.
- If remaining rows exist, show Upload paused and Continue Upload.
- Upload Weights with an existing batch id processes that existing batch and does not create a new batch.
- Draft Review uses local owner-input counts; Upload Progress uses backend batch progress counts.

## P0 Simple Bulk Upload UX - 2026-06-29

Mode: P0 usability/reliability polish on the durable bulk rail. No migration, production data rewrite, customer send, public post, payment/deposit change, reservation change, unrelated lifecycle/purpose write, Phase 3A.6, CHARLIE/FRED/ledger work, screenshot, external source, asset, `.env`, or `.claude` change is approved.

Owner live finding after durable rail deploy:

- Owner restored the 2026-06-22 draft and pressed Save Draft.
- The page then required Stage Batch and exposed backend mechanics.
- Batch Review showed confusing zero draft counts while still showing 42 remaining rows and 31 blocked rows.
- There was no obvious action to finish the upload.

Final UX rule:

- Keep Supabase staging and chunk processing internally.
- Owner-facing actions are Save Draft, Upload Weights, Download Draft, and Import Draft.
- Upload Weights must stage and auto-process chunks in one flow.
- Continue Upload appears only when processing is interrupted or rows remain.
- Duplicate weights are shown as Already recorded for this date, not scary errors.
- Blank/no-change rows are skipped clearly.

## P0 Supabase-First Durable Bulk Rail - 2026-06-28

Mode: P0 data-loss reliability build. Owner approved a narrow additive Supabase migration for bulk-weight batch staging/audit only. No production data writes, customer sends, public posts, payment/deposit changes, reservations, unrelated lifecycle/purpose writes, Phase 3A.6, CHARLIE/FRED/ledger work, screenshots, external sources, assets, `.env`, or `.claude` changes are approved.

Second live failure after JSON-safe hotfix:

- Owner restored the saved draft and attempted a 73-row upload dated 2026-06-22.
- About 21 rows included pen changes.
- The old synchronous endpoint `POST /api/pig-weights/weights-batch` still returned non-JSON HTML with HTTP 500.
- Batch Review showed 116 visible, 73 actionable, 0 weight rows, 0 pen changes, 0 processed, 43 skipped, 0 blocked, 0 failed.
- Draft recovery protected the typed rows, but the backend upload path remained unreliable.

Final decision:

- The synchronous Google Sheets upload path is not reliable enough for large weekly batches.
- The new durable rail stages the full browser draft and every row in Supabase before processing.
- Processing happens in chunks of 10 by default, never as one opaque 73-row request.
- Row status and result details remain durable so failures can be retried without wiping the batch.
- Google Sheets remains a downstream compatibility target during chunk processing.
- Import Draft and Download Draft remain required so the owner never has to retype a large batch.

Pressure-test gate:

- 73 rows plus 21 pen changes must stage durably.
- Chunk processing must handle only a small number of rows per request.
- Failure after row 60 must leave batch/rows available with failure details.
- Retry must not reprocess successful rows.
- HTML/non-JSON responses must keep draft and staged batch state.

## OP-1.2 Evidence Push - 2026-06-28

Mode: read-only evidence gathering. No code edits, database writes, migrations, customer sends, public posts, payment/deposit changes, reservations, lifecycle writes, screenshots, external sources, or assets were touched.

## Commands And Tests Run

- `git fetch origin`
- `git branch --show-current`
- `git status --short --untracked-files=all`
- `git log --oneline --decorate -12 origin/main`
- `git diff --name-only origin/main`
- `git diff --stat origin/main`
- `rg -n "pilot readiness|readiness|meat-leads|Chatwoot|sales_leads|customer_name|bulk weight|movement|DEFAULT_ALLOCATION_SETTINGS|SALES_STOCK_SUMMARY|SALES_STOCK_TOTALS|price book|owner_logout" app.py modules templates static tests docs`
- Read-only env availability check. Values were not printed.
- Read-only Supabase summary query. Values were summarized and IDs masked.
- Read-only Google Sheets service summary using clean worktree code and the original repo credential path.
- Non-mutating mocked bulk-weight 71-row pressure probe.
- Non-mutating mocked SAM pilot readiness source-failure probe.
- `tests.test_owner_access`: passed, 23 tests.
- `tests.test_sales_transaction_routes`: passed, 62 tests.
- `tests.test_pig_weights_bulk_service`: passed, 8 tests.
- `tests.test_pig_allocation_readiness_service tests.test_meat_price_book`: passed, 13 tests.
- `tests.test_sam_meat_runtime`: passed, 55 tests.
- `tests.test_oom_sakkie_routes`: passed, 142 tests.
- `tests.test_meat_match_engine tests.test_meat_documents`: passed, 26 tests.

The clean OP-1 worktree has no local `.\venv\Scripts\python.exe`, so tests were run with `..\amadeus-pig-tracking-system\venv\Scripts\python.exe` while keeping the working directory on the clean OP-1 branch.

## Read-Only Supabase Findings

Supabase access was available after loading the original repo `.env`; no secret values were printed.

Tables present:

- `oom_sakkie_sales_leads`
- `oom_sakkie_sales_lead_events`
- `oom_sakkie_meat_price_book_entries`

Safe counts:

- sales leads: 31
- sales lead events: 188
- meat price book entries: 5

Lead status counts:

- `new`: 20
- `interested`: 11

Owner-provided label inspection:

- Sinethemba, Pappa G, and Thando all matched actual sales lead rows.
- All three are `status=new`, `campaign_source=inbound_chatwoot`, `channel=chatwoot`, `whatsapp_window_state=open`.
- Chatwoot conversation IDs were masked and not reported.
- All three had `interest_product_type=unknown`.
- All three had no cut set, no location, and no timing fact.
- All three had notes present, but raw note text was not printed.

Lead quality implication:

- Weak/vague chats are currently becoming sales lead rows, not just raw conversation events.
- Current minimum-facts rule is too broad for the owner-approved qualified-meat-lead rule.

Price book findings:

- Active configured price-book groups exist for assisted slaughter, custom cut, full carcass, half carcass, and half carcass Set A.
- Price values were not printed.

## Read-Only Google Sheets / Service Findings

The clean worktree did not include `service_account.json`; the original repo does. Clean worktree code was run with `GOOGLE_SERVICE_ACCOUNT_FILE` pointing at the original credential path. No writes were made.

Sales dashboard:

- `/api/pig-weights/sales-dashboard` service shape has top-level `success`, `summary`, and `totals`.
- `totals_rows=6` and `summary_rows=21`.
- Categories include Newborn, Young Piglets, Weaner Piglets, Grower Pigs, Finisher Pigs, and Ready for Slaughter.
- Price ranges are present in the sales dashboard data.
- Current dashboard source is category/table stock data, not an explicit meat-ready-stock model.

Pig allocation readiness:

- Read succeeded.
- Current thresholds source is `code_defaults`.
- Current defaults: live sale 60kg, meat 55-70kg, slaughter 80-95kg, stale weight 45 days.
- Readiness row count: 217.
- Readiness buckets included Needs Data, Needs Classification, Growing, Livestock Candidate, Meat Candidate, Retain / Breeding Candidate, and Exited.
- Current Meat Candidate count from service summary: 3.

## Non-Mutating Pressure Probe Findings

Bulk weights 71-row mocked probe:

- Accepted rows: 71.
- Simulated failure after 60 save calls.
- Current service still returned HTTP 201 and `success=true`.
- Result had `saved_count=60`, `failed_count=11`, and `failed_rows_len=11`.
- Audit payload was present because audit write was mocked.

Bulk implication:

- Current rail does record failed rows, but it still presents partial success as success.
- Build direction is clear: add operation id, stronger summary, retry/idempotency, and make partial writes impossible to miss.
- Recommended direction: two-phase approach, immediate Sheets safety patch plus Supabase durable rail if pressure testing shows Sheets remains structurally unreliable.

SAM pilot readiness mocked probe:

- A simulated per-lead contract read exception raised out of `get_meat_pilot_readiness()`.
- Current service did not degrade that source or continue.
- This reproduces the failure class behind a 500 without touching live data.

SAM pilot implication:

- Root cause class is confirmed: per-lead source exceptions can break the full readiness response.
- Build direction is clear: per-source/per-lead degraded handling and tests.

## Confidence Changes

- OP-001 raised to 96% because actual Supabase lead rows confirm weak owner-labeled chats exist as lead rows with unknown product and missing actionable facts.
- OP-002 raised to 96% because route/service/audit behavior and a 71-row mocked failure path are proven.
- OP-003 raised to 97% because thresholds, affected services, and owner boundary rule are confirmed.
- OP-007 raised to 96% because dashboard source, allocation source, current categories, current meat candidates, and dependency on OP-003 are confirmed.
- OP-008 raised to 96% because current price sources, weight/status sources, and owner freshness/value rules are confirmed.
- OP-009 raised to 96% because a targeted non-mutating failing probe proves per-lead source exceptions bubble instead of degrading.
- OP-010 remains 98% because `/` dashboard route and current logout redirect are confirmed.

## Evidence Gaps

- OP-004 still needs owner workflow inspection before build.
- OP-005 still needs live UI/browser inspection before build.
- OP-006 still needs live UI/browser inspection before build.
- OP-002 implementation should still include a pre-merge pressure-test report with 71-row, duplicate, partial failure, and retry cases.
- OP-001 implementation should still include anonymized one-word/vague/duplicate/real-intent fixture tests.

## No-Write Confirmation

No INSERT, UPDATE, DELETE, UPSERT, TRUNCATE, schema change, migration, customer send, public post, payment/deposit change, stock/reservation change, or lifecycle/purpose write was performed.

## P0 One-Button Bulk Owner Flow - 2026-06-29

Owner live finding after staged-batch auto-process deploy:

- The page still showed too much backend workflow: Continue Upload, batch id, `non_json_response`, and technical counts.
- Process call returned HTTP 500/non-JSON from `/api/pig-weights/bulk-batches/2241aeab-4f40-4797-882d-1588a17abbd0/process`.
- Main owner message said the draft was saved, but upload progress also said no rows were waiting. This was contradictory and not acceptable.

Read-only Supabase inspection of batch `2241aeab-4f40-4797-882d-1588a17abbd0`:

- Batch status: `processing`.
- Row statuses: 31 `duplicate`, 43 `skipped`, 10 `processing`, 32 `staged`.
- Action/status counts: 31 duplicate weights, 43 skipped blank/no-change, 1 duplicate-weight movement stuck in `processing`, 9 weight rows stuck in `processing`, and 32 weight rows still `staged`.
- No production batch processing was run during inspection.

Root cause:

- Owner-facing frontend still exposed backend mechanics and technical error/status strings.
- Interrupted process requests could leave rows in `processing`; the next process call only selected `staged` rows, so those rows could remain stuck.
- The process route is wrapped for JSON app-level errors, but platform/server interruptions can still return HTML; the frontend must treat this as a resumable interruption, not as a final owner-facing technical error.

Fix direction:

- Keep one owner action: `Upload Weights`.
- Hide separate Continue Upload from the primary workflow.
- `Upload Weights` stages if needed, resumes existing batch ids, processes chunks automatically, retries transient failures, and pauses safely with the draft/batch preserved.
- Backend processing treats interrupted `processing` rows as resumable and persists progress after each row.

## GS-MIG-5 Controlled Initial Farm Import - 2026-06-29

Mode: controlled Supabase canonical import after owner approval. Google Sheets was read only. No app routes were cut over.

Import batch:

- `GS-MIG-5-2026-06-29`

Pre-import safety:

- Canonical farm tables were verified empty before execution.
- The import runner refuses to import into non-empty canonical target tables.
- `LOCATION_HISTORY` accounting was tightened so movement rows cannot be silently dropped before the review gate.
- Dry-run confirmed 179 of 179 movement source rows accounted.

Import result:

- `pens`: 20
- `pigs`: 217
- `farm_products`: 3
- `app_settings`: 18
- `litters`: 17
- `mating_events`: 15
- `pig_weight_events`: 1,190
- `pig_location_events`: 179
- `pig_medical_events`: 261

Post-import verification:

- `pig_current_state`: 217 rows
- `pig_latest_location_events`: 113 rows
- `pig_latest_weight_events`: 155 rows
- `pig_weight_events` import batch `GS-MIG-5-2026-06-29`: 1,190 rows

Held out for review:

- 9 conflicting same-pig/same-date weight groups remain excluded.
- 25 same-weight duplicates were auto-resolved by importing one canonical event.
- Missing-`Pig_ID` weight quarantine is 0 after owner cleanup.

Tests and commands:

- `tests.test_google_sheets_farm_import_dry_run`: 16 passed
- `tests.test_google_sheets_farm_import_execute`: 3 passed
- Python compile check for import scripts: passed
- Controlled import dry-run: passed
- Controlled import execute: passed

No-unsafe-action confirmation:

- No Google Sheets writes.
- No customer sends, public posts, payments, deposits, reservations, or lifecycle/purpose writes.
- No app route cutover.
- No destructive SQL.

Next:

- GS-MIG-6 should create the owner/admin review output for the 9 conflicting-weight groups and verify imported Supabase rows before any route reads are switched from Google Sheets.

## GS-MIG-8 Order/Sales Supabase Cutover - 2026-06-29

Mode: Supabase cutover after PR #27. Google Sheets remains fallback only where the new Supabase boundary is unavailable or not yet safe.

Live order import:

- Import batch: `IMPORT-20260629-LIVE-ORDERS-V1`
- Imported/upserted to Supabase: 26 `orders`, 103 `order_lines`, 38 `order_intakes`, 11 `order_intake_items`, 6 `order_documents`, 62 `order_status_logs`, and 21 `sales_pricing` rows.
- Google Sheets was read only during import.

App cutover in progress:

- `modules.orders.order_read` now prefers Supabase canonical `orders` and `order_lines`.
- `modules.documents.document_service` now prefers Supabase `order_documents` for document metadata reads.
- `modules.documents.document_service` now prefers Supabase `app_settings` for document settings and Supabase `order_documents` for generated document metadata writes and sent-status updates.
- `modules.reports.report_service` now prefers Supabase `order_status_logs` for daily transition summaries.
- `modules.orders.order_write`, `order_line_sync`, `order_reservation`, `order_lifecycle`, and `order_status_log` now use guarded Supabase write helpers when available, with Sheets fallback.
- `modules.orders.order_intake_service` now uses a Supabase intake store for context/update/reset when available, with Sheets fallback.
- `modules.sales.sales_transaction_lifecycle` now prefers Supabase `pigs` for slaughter exit confirmation/reconciliation, with Sheets fallback.
- `modules.pig_weights.mating_service` now prefers Supabase `mating_events` and `pig_location_events` for mating creation, pregnancy status updates, litter-link updates, and mating-related movements, with Sheets fallback.
- `modules.pig_weights.pig_weights_service` direct farm write routes now prefer Supabase canonical farm tables for pig/product/pen creation, single weights, treatments, and movements, with Sheets fallback.

Live read-only smoke:

- `order_read.list_orders()` returned 26 orders.
- First order detail returned source `supabase_canonical`.
- Supabase table counts matched the live order import payload.
- Daily order summary generated successfully from the Supabase-backed read path.

No-unsafe-action confirmation:

- No destructive SQL.
- No customer sends.
- No public posts.
- No payments/deposits.
- No manual production reservation/lifecycle action was executed by scripts.
- No Google Sheets writes were run from tests.

Remaining risks:

- Litter lifecycle/piglet correction workflows and formula-specific newborn-health attention replacement still need separate Supabase service work.

Document rail checkpoint:

- Added a guarded Supabase document write/settings adapter.
- `get_document_settings()` reads `app_settings` first, with `SYSTEM_SETTINGS` fallback.
- `append_order_document()` inserts/upserts generated quote/invoice metadata into `order_documents` first, with `ORDER_DOCUMENTS` fallback.
- `mark_document_sent()` updates `order_documents` first, with `ORDER_DOCUMENTS` fallback.
- Quote generation now reads order lines from Supabase order detail first, with `ORDER_LINES` fallback.
- Focused and broader order/document tests passed.

Sales transaction lifecycle checkpoint:

- Added additive migration `202606290002_add_pig_exit_fields.sql` for nullable `pigs` exit metadata.
- Slaughter sale pig-exit confirmation and closed-sale reconciliation now read/update Supabase `pigs` first, including status, on-farm flag, exit date/reason/order id, carcass weight, and notes.
- Existing Google Sheets `PIG_MASTER` path remains fallback if the Supabase rail or exit-field migration is unavailable.
- Focused sales lifecycle and sales transaction route/service tests passed with local owner access disabled for protected test routes.

Breeding mutation checkpoint:

- Added a guarded Supabase mating write adapter.
- `save_new_mating()` inserts into `mating_events` first and logs optional sow/boar movements into `pig_location_events`.
- `assume_pregnant()`, `mark_not_pregnant()`, and `link_litter_to_mating()` update `mating_events` first.
- Existing `MATING_LOG` and `LOCATION_HISTORY` paths remain fallback if the Supabase rail is unavailable.
- Focused mating service, mating route, breeding analytics, farm Supabase read, and frontend route-contract tests passed.

Direct farm write checkpoint:

- Added a guarded Supabase farm write adapter for `pigs`, `pens`, `farm_products`, `pig_weight_events`, `pig_medical_events`, and `pig_location_events`.
- `save_new_pig()`, `save_new_product()`, `save_new_pen()`, `save_weight_entry()`, `save_weight_entry_with_optional_move()`, `save_treatment_entry()`, and `save_movement_entry()` now prefer Supabase.
- Healthy Supabase duplicate-weight checks avoid the legacy `WEIGHT_LOG` duplicate scan.
- Existing Google Sheets paths remain fallback when the Supabase write rail is unavailable.
- Focused farm write cutover, duplicate-weight, bulk-weight, litter-service, and frontend route-contract tests passed.

Litter lifecycle write checkpoint:

- Added additive migration `202606290003_add_litter_lifecycle_fields.sql` for nullable litter/wean/earmark fields on canonical farm tables.
- Added guarded Supabase update helpers for pig and litter field updates plus litter newborn health medical-event inserts.
- Litter birth-count correction, stillborn reclassification, purpose review decisions, litter weaning, pig death/removal, litter piglet death, piglet sex count updates, piglet tag assignment, and newborn health actions now prefer Supabase writes when available.
- Existing Google Sheets paths remain fallback when the Supabase write rail is unavailable.
- Focused Supabase write cutover and full litter-service tests passed.

Migration apply checkpoint:

- PR #28 merged as `9733173` on `main`.
- Applied `202606290002_add_pig_exit_fields.sql` successfully on 2026-06-29.
- Initial apply of `202606290003_add_litter_lifecycle_fields.sql` failed before commit because the `pig_current_state` view replacement changed the existing column order.
- Corrected `202606290003_add_litter_lifecycle_fields.sql` so existing view columns stay in place and new lifecycle columns append at the end.
- Re-applied `202606290003_add_litter_lifecycle_fields.sql` successfully on 2026-06-29.
- Read-only verification confirmed both migration log entries exist, the new pig lifecycle/exit columns exist, and `pig_current_state` exposes lifecycle fields after the original current-state columns.

Irrigation status cutover checkpoint:

- `get_irrigation_status()` now defaults to Supabase-first `auto` mode instead of defaulting straight to Google Sheets.
- If Supabase has plan rows for the requested day, the route returns Supabase read-only status and does not read Sheets.
- If Supabase has no plan rows or is unavailable, the existing Google Sheets fallback remains.
- Hardware control remains disabled: read-only status only, no pump/valve/control writes.
- Tests passed: `tests.test_irrigation_telemetry`, `tests.test_workflow_contracts`, and `tests.test_frontend_route_contracts` (68 tests).

## GS-MIG-6 Conflicting Weight Review And Reconciliation - 2026-06-29

Mode: read-only Supabase/Google Sheets reconciliation. No writes or app route cutover.

Generated report:

- `docs/06-operations/GS_MIG_6_CONFLICTING_WEIGHT_REVIEW.md`

Reconciliation result:

- All imported table counts match the GS-MIG-5 policy payload.
- `pig_current_state`: 217 rows
- `pig_latest_location_events`: 113 rows
- `pig_latest_weight_events`: 155 rows
- All 9 conflicting-weight keys have 0 imported canonical rows.
- Route cutover remains blocked until owner/admin review and route-by-route shadow verification.

Conflicting-weight review IDs:

- `CW-001` `PIG-2026-0874` on `2026-02-02`
- `CW-002` `PIG-2026-12D8` on `2026-03-23`
- `CW-003` `PIG-2026-3E84` on `2026-03-02`
- `CW-004` `PIG-2026-42B7` on `2026-05-04`
- `CW-005` `PIG-2026-6D24` on `2026-05-11`
- `CW-006` `PIG-2026-8FFC` on `2026-02-09`
- `CW-007` `PIG-2026-A5EA` on `2026-03-17`
- `CW-008` `PIG-2026-E926` on `2026-05-11`
- `CW-009` `PIG-2026-EFB3` on `2026-05-25`

No-unsafe-action confirmation:

- No Google Sheets writes.
- No Supabase writes.
- No app route cutover.
- No customer sends, public posts, payments, reservations, or lifecycle/purpose writes.

## GS-MIG-12 Farm Dashboard Summary Supabase Cutover - 2026-06-29

Mode: route-facing read cutover. No migrations, production writes, Google Sheets writes, customer sends, public posts, payments, reservations, lifecycle/purpose writes, Phase 3A.6, CHARLIE/FRED/ledger work, screenshots, external sources, assets, `.env`, or `.claude` changes.

Scope:

- `/api/pig-weights/dashboard` summary now prefers Supabase canonical reads when `DATABASE_URL` is available.
- The Supabase summary reads `pig_current_state`, `pigs` exit metadata, and reserved `order_lines` to compute on-farm counts, animal-type counts, monthly pig exits, lifecycle outcomes, and reserved-pig counts.
- Existing sales transaction totals remain sourced from the Supabase-backed sales transaction summary service.
- The existing Google Sheets `PIG_OVERVIEW`, `SALES_AVAILABILITY`, and `PIG_MASTER` summary path remains fallback when Supabase is unavailable or the read fails.

Tests:

- Added focused tests proving the Supabase summary calculation and proving the public dashboard summary does not read Sheets when Supabase is available.

## GS-MIG-13 Purpose Review Supabase Validation - 2026-06-29

Mode: route-facing validation cutover. No migrations, production writes during tests, Google Sheets writes, customer sends, public posts, payments, reservations, unrelated lifecycle/purpose writes, Phase 3A.6, CHARLIE/FRED/ledger work, screenshots, external sources, assets, `.env`, or `.claude` changes.

Scope:

- Purpose-review apply now validates requested pigs from Supabase `pig_current_state` joined to `pigs` when Supabase reads are available.
- The existing `PIG_MASTER` validation path remains fallback when Supabase is unavailable or the read fails.
- Existing guarded Supabase purpose update rail remains the preferred write path when writes are available; Sheets remains fallback only when the Supabase write rail is unavailable.

Tests:

- Added focused test proving purpose-review apply does not read Sheets and writes through the Supabase update helper when Supabase read/write rails are available.

## GS-MIG-14 Litter Create Supabase Transaction - 2026-06-29

Mode: route-facing write cutover. No migrations, production writes during tests, Google Sheets writes during tests, customer sends, public posts, payments, reservations, unrelated lifecycle/purpose writes, Phase 3A.6, CHARLIE/FRED/ledger work, screenshots, external sources, assets, `.env`, or `.claude` changes.

Scope:

- New litter creation now attempts a Supabase transaction first when Supabase read/write rails are available.
- The transaction inserts the litter and generated piglet rows together, preserving live piglets and stillborn history rows.
- Existing Google Sheets `LITTER_REGISTER`/`PIG_MASTER` creation remains fallback when Supabase is unavailable or the transaction fails.
- Existing mating/litter link behavior is preserved after successful creation.

Tests:

- Added focused test proving new litter creation does not read or write Sheets when the Supabase transaction rail is available.
