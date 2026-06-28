# Operational Fixes Evidence Log

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
