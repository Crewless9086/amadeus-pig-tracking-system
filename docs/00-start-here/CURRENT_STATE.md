# Current State

## Purpose

This document is the live operational truth of the project. It summarizes what is documented, what is working, what is risky, and what must be built next.

## System Status

| Area | Status | Notes |
| --- | --- | --- |
| Documentation structure | Stable | `docs/` is now the canonical source of truth. |
| Google Sheets docs | Good baseline | Sheet files, formulas, ownership, field standards, and business rules are documented. |
| n8n workflow docs | Good baseline | Four workflow exports and suite-level rules are documented. |
| Backend order docs | Good baseline | Current API behavior, known gaps, and refactor direction are documented. |
| Live order system | Stabilizing | Reject, customer cancel, first-turn create-with-lines, payment method capture, send-for-approval, lifecycle guards, auto-reservation, outbound notifications, quote/invoice generation, and document delivery are implemented and have been live-verified through the documented phases. |
| Web app | Operational slices improving | Orders list/detail usability is complete through Phase 6.2. Breeding board Phase 8D is live-verified on a real repeat-service case. |
| Media workflow | Disabled | `1.3` is official but must remain disabled until fixed and tested. |

## Completed Documentation Work

The following documentation areas are now usable as planning inputs:

- `docs/03-google-sheets/`: Google Sheets schema, ownership, formulas, fields, and per-sheet docs.
- `docs/04-n8n/`: n8n suite map, workflow rules, data flow, node responsibilities, protected logic, and four workflow exports.
- `docs/02-backend/`: backend API structure, order logic, data models, module structure, and refactor plan.

## Current Build Priority

The next build work should continue one documented phase slice at a time.

Reason:

- orders remain live and profit-critical
- pig and breeding operations are now becoming daily-use web app workflows
- Oom Sakkie and farm telemetry workflows need careful integration without breaking live sales or Telegram routing
- Google Sheets limits and future Supabase migration need to be handled deliberately, not through rushed rewrites

## Known Critical Order Gaps

### Reject Releases Reserved Lines

Status: implemented and live-verified.

Confirmed behavior:

- `reject_order()` blocks completed orders from being rejected
- linked order lines become `Line_Status = Cancelled`
- linked line reservations become `Reserved_Status = Not_Reserved`
- `ORDER_MASTER.Reserved_Pig_Count` becomes `0`
- `SALES_AVAILABILITY` recovers and makes pigs available again through the formula chain
- `ORDER_STATUS_LOG` records the rejection

### Customer Cancellation Is Implemented And Live-Verified

Current backend behavior:

- `cancel_order()` provides a dedicated customer cancellation action
- `POST /api/orders/<order_id>/cancel` is available
- `Order_Status = Cancelled`
- `Approval_Status = Not_Required`
- `Payment_Status = Cancelled`
- linked non-cancelled/non-collected lines are cancelled
- linked line reservations are set to `Not_Reserved`
- `Reserved_Pig_Count` is reset to `0`
- `ORDER_STATUS_LOG` records customer cancellation when state changes

Current n8n wiring:

- `1.2 - Order Steward` has a `cancel_order` branch calling `POST /api/orders/{order_id}/cancel`
- `1.0 - Sam Sales Agent` uses `pending_action = cancel_order` for two-turn confirmation
- `CANCEL_ORDER` is evaluated before create/update routes
- stale cancel confirmation is cleared through `CLEAR_PENDING`
- Chatwoot order attributes survive escalation and human reply through the full snapshot rule
- cancellation after escalation was live-verified against `ORD-2026-367706`

First-turn draft creation with lines:

- `1.0` now routes complete first-turn requests with `requested_items[]` to `1.2` using `action = create_order_with_lines`
- `1.2` owns the full create + sync operation: create `ORDER_MASTER`, sync `ORDER_LINES`, then return one combined result
- top-level `success` is true only when both create and sync succeed
- live verification passed on 2026-04-29 with `ORD-2026-879091`; three `ORDER_LINES` rows were created with `match_status = exact_match`

Payment method capture:

- `Payment_Method` is stored on `ORDER_MASTER` as the source of truth
- Chatwoot `custom_attributes.payment_method` mirrors the order value for conversation continuity
- `Cash` and `EFT` capture are live-verified
- next-turn readback from Chatwoot is live-verified
- cancel-pending and escalation paths preserve `payment_method`
- backend lock guard is live-verified: `payment_method` cannot be changed once the order is beyond `Draft`
- no-draft handling is live-verified: Sam does not write payment method without an active draft

Send for approval from Sam:

- `1.0` detects customer send-for-approval intent and routes to `SEND_FOR_APPROVAL`
- `1.2` calls backend `send_for_approval` with `neverError` and `continueOnFail` enabled so backend guards return as data
- backend validates draft status, payment method, customer name, collection location, and at least one non-cancelled order line
- happy path live verification passed on 2026-04-30 with `ORD-2026-377DA3`; order moved to `Pending_Approval`, Chatwoot status updated, and Sam said the order was sent for approval, not approved
- already-pending regression check passed
- missing payment method regression failed, then was fixed and live re-tested on 2026-05-04: `Code - Decide Order Route` now sets approval preflight `reply_instruction` when `send_for_approval_intent = true` but `sendForApprovalReady = false`; Sam asks for Cash/EFT, backend is not called, and Draft status is preserved
- backend `400` customer-safe reply regression passed live re-test on 2026-05-04: backend rejected missing `Collection_Location`, `backend_success = false` path returned a safe missing-field reply, and Sam did not say the order was sent

Approve/reject lifecycle direction:

- Phase 1.5 lifecycle guards — **Complete And Live-Verified** (see `NEXT_STEPS.md` §1.5): approval only from `Pending_Approval`, payment lock beyond `Draft`, reject/cancel blocked for `Completed`; outbound notifications stay in Phase 1.9
- Phase 1.8 approval auto-reservation is complete and live-verified
- approval should auto-reserve active order lines, because approval means the farm accepts and commits to the order
- repo implementation now approves first, then attempts auto-reservation; approval does not roll back if reservation fails or partially fails, and backend returns `reserve_warning` for the admin web app
- live mixed-line verification passed on 2026-05-09 with `ORD-2026-102250`: approval succeeded, one active line reserved, one cancelled line skipped, `Reserved_Pig_Count = 1`, and `ORDER_STATUS_LOG` recorded the warning follow-up
- clean all-eligible verification passed on 2026-05-09 with `ORD-2026-7C79A8`: two active lines reserved, `Reserved_Pig_Count = 2`, and no warning returned
- all-ineligible verification passed on 2026-05-09 with `ORD-2026-0FB697`: order approved, cancelled lines remained not reserved, `Reserved_Pig_Count = 0`, and `ORDER_STATUS_LOG` recorded the no-reservation warning
- live `ORDER_MASTER`, `ORDER_LINES`, and `ORDER_STATUS_LOG` headers matched `docs/03-google-sheets/sheets/` during Phase 1.8 verification; `ORDER_MASTER.Payment_Method` is live and required, and `ORDER_MASTER.ConversationId` is live as the Phase 1.9 Chatwoot lookup key
- approval/rejection customer notifications use a separate outbound n8n workflow triggered by backend webhook, not Sam's inbound `1.0` workflow
- Phase 1.9 outbound approval/rejection notifications are complete and live-verified
- new draft orders store `conversation_id`, approvals/rejections call `ORDER_NOTIFICATION_WEBHOOK_URL`, and delivery failures are logged as warnings without rolling back the order transition
- live Phase 1.9 verification passed on 2026-05-09: direct `1.4` webhook test returned `sent = true`; `ORD-2026-36CDE4` approval sent the customer notification and reserved one line; `ORD-2026-C3CEDF` rejection sent the customer notification and cancelled/released one line
- production backend must keep `ORDER_NOTIFICATION_WEBHOOK_URL=https://charln.app.n8n.cloud/webhook/order-notification` configured

### Split Requested Item Sync Needs Hardening

Known risk:

- split items such as `primary_1` and `primary_2` have not always synced correctly
- female/secondary split rows have been missing or not updated in some tests

Required behavior:

- all split item keys must be preserved
- repeated syncs must not create duplicates
- stale lines must be released/cancelled before replacement
- partial matches must not silently appear complete
- line totals must match requested quantity before Sam confirms success

### Sam Needs Safer Order Context

Approved direction:

- Sam should get order context through `1.2 - Amadeus Order Steward` and backend review actions
- direct production access to `ORDER_OVERVIEW` should not be the first choice

Reason:

- backend can verify customer/order ownership
- backend can return only safe, relevant fields
- backend responses are easier to test than uncontrolled AI sheet reads

### Sales Agent Reply Payload — closed (Phase 1.7, 2026-05-07)

**Resolved:** `Code - Slim Sales Agent User Context` feeds Sam **`OrderStateSummary`** + **`StewardCompact`**; see `docs/04-n8n/DATA_FLOW.md` §`1.0` Sales Agent Input Contract. Raw/debug payloads stay upstream of the slim node.

## Web App Current Concern

The app must become useful for daily operations. It should help with:

- viewing orders clearly
- viewing matings in a clear breeding board for pregnancy checks, farrowing preparation, movement planning, and repeat-service decisions
- understanding reservation status
- approving/rejecting/cancelling orders safely, with order detail actions visible only when backend rules allow them
- releasing pigs correctly
- showing logs/history
- producing practical farm printouts, starting with a pre-weighing weekly weight sheet that has blank capture columns and can be printed from a phone or laptop
- reducing manual debugging work

Do not focus on app polish before the related backend behavior is correct.

## Next Decision Point

Pick the next item from `docs/00-start-here/NEXT_STEPS.md`.

Current position:

- Phase 7.3D is complete and live-verified.
- Phase 7.3E weather was triaged; weather is working, while Sunsynk is deferred to a dedicated backend/data/Supabase review.
- Phase 8D is live-verified: Baby's real mating was safely marked `Not_Pregnant` / `Repeat_Service` on 2026-05-20 and remained in Kraam Saal 05.
- Phase 8D follow-up is deployed and live-verified: Baby's new mating `MAT-2026-9EFC4E` now shows formula-derived expected dates correctly in the live API.
- Phase 9.1A is live-verified: real litters `LIT-2026-9E4A` and `LIT-2026-EB92` generated the expected piglet rows with `Purpose = Unknown`.
- Phase 9.1B is deployed and browser-verified: dashboard litter attention reads `LITTER_OVERVIEW`, and litter tiles open the litter detail page.
- Phase 9.1C is deployed and browser-verified: litter detail now shows attention metadata and provides a backend-owned `Mark as Weaned` action that updates `LITTERS` and linked active/on-farm `PIG_MASTER` piglets with the chosen wean date/count. Purpose/classification review remains a later slice. A 2026-05-30 audit confirmed `LIT-2026-OTY0` and `LIT-2026-0LBF` were record-reconciliation attention items and `LIT-2026-8A0F` needs piglet tag numbers. Owner reconciled `LIT-2026-OTY0` and `LIT-2026-0LBF`; dashboard logic now only keeps `Weaned - review purpose` when active/on-farm piglets still have blank or `Unknown` purpose, so older litters with accepted `Sale` / `Grow_Out` / `Breeding` purposes no longer wait on the future auto-classification function. `LIT-2026-8A0F` remains the legitimate visible attention item until its piglets are tagged.
- Lifecycle automation direction is captured in `NEXT_STEPS.md`: future piglet death, post-weaning death, weaning, sales, slaughter, and meat-stream actions should update the correct source records/logs and feed sow/boar/litter/bloodline outcome reporting. Pre-weaning deaths must keep the pig row because they are part of born-alive survival history.
- Phase 9.2A is deployed and owner-verified: pig dropdown APIs and labels now include current pen context and three-slot numeric tag display.
- Phase 9.2B is deployed and owner-verified: `/pigs` now displays numeric-only tags as three digits, sorts the list with numeric-aware tag order, and keeps profile links on unchanged `pig_id` values.
- Phase 9.3 is deployed and owner-verified: the weight form shows the selected pig's current pen beside `Moved To Pen (Optional)` without changing the save payload.
- Phase 9.3B is deployed and owner-verified: `/pig-weights` weight input blocks mouse-wheel value changes, hides number spinners, and shows a top save action after the required fields while preserving the existing save payload.
- Phase 9.4 current slice is deployed and owner-verified: read-only weight report endpoint and `/weight-report` page include visual usability refinements, duplicate prevention is live, and numeric pig tags display correctly as three digits. Full edit/delete/void audit, interactive report rows, sortable report headers, and feed-guidance planning remain parked for later phases.
- Phase 9.5 is deployed/browser-visible: the dashboard monthly sales count now shows total sales exits plus livestock, slaughter/abattoir, and future meat streams from `PIG_MASTER` exits. Follow-up 9.5B is planned for clearer sales stream counts and Rand values once each stream's value source is defined.
- Phase 9.5B planning is updated: keep current pig-exit counts honest, do not fake Rand totals from pig counts, define slaughter/abattoir sale logging first, and align future value cards with a transaction model/Supabase rather than a complex Google Sheets-only patch.
- Phase 9.5B1 is deployed and owner-verified: dashboard wording now says `Sales Exits This Month`, `Livestock Exits`, `Slaughter Exits`, and `Meat Exits`; backend counts are unchanged.
- Phase 9.5B2 planning is captured: slaughter/abattoir sales need a transaction/value source before dashboard Rand totals; preferred future direction is Supabase-backed `sales_transactions` with linked pigs/items rather than a Google Sheets-only patch.
- Phase 9.6A is deployed and browser-verified: `/print-sheets` provides a read-only weekly weight capture sheet with English labels, all-active default, multi-pen filtering, browser print support, and no Google Sheets writes.
- Phase 9.6C is deployed and intentionally left open for live testing: `/bulk-weights` follows the printable sheet row order, allows local browser draft-saving, skips rows with no weight, validates duplicates/mistakes before commit, and uploads accepted rows as one deliberate batch. Local route smoke and the full local unittest suite passed on 2026-06-01; owner will live-test with real weighing data before closure.
- Phase 9.7 lifecycle outcome tracking is now the planned next farm-efficiency slice after live checks: start with a current-state audit/action matrix for death/removal, sale/live-stock exit, slaughter/abattoir exit, weaning outcome, and later meat-stream movement. The goal is backend-owned, auditable outcome actions that feed pig, litter, sow, boar, dashboard, and sales reporting without disconnected manual edits.
- Phase 9.7A audit source is created in `docs/02-backend/PIG_LIFECYCLE_OUTCOME_PLAN.md`: born-alive piglet creation, litter weaning, and order-based live-stock sale completion already have backend-owned actions; slaughter transactions do not yet update `PIG_MASTER`; no complete death/removal action was found. Recommended next build is 9.7B controlled death/removal on pig detail.
- Phase 9.7B controlled death/removal action is deployed-visible and dry-run verified against a real active pig, but still awaiting a real write case: `/pig/<pig_id>` has a lifecycle outcome form for active/on-farm pigs, and `POST /api/pig-weights/pig/<pig_id>/lifecycle/death` updates `PIG_MASTER` status/on-farm/exit fields and notes while preserving the pig row and litter/parent links. The endpoint now supports `dry_run = true`; dry-run against `PIG-2026-42B7` returned the planned removal update with `rows_updated = 0`, and readback confirmed the pig stayed `Active` / `On_Farm = Yes`. Real write closure should wait for an actual farm case or an explicitly approved test pig.
- Phase 9.7C slaughter pig-exit confirmation is local and ready for deploy/browser check: `/sales/slaughter/<sale_id>` has an explicit `Pig Exit Confirmation` form for open slaughter sales, and `POST /api/sales-transactions/<sale_id>/confirm-pig-exits` reads the Supabase sale/items then updates linked `PIG_MASTER` rows to `Slaughtered` / off-farm only when all linked pigs are still active/on-farm. Closed paid/completed/cancelled sales are blocked by 9.7E instead of keeping the normal action available.
- Phase 9.7D read-only lifecycle outcome dashboard feedback is deployed and getting layout refinement: the home dashboard herd panel shows `Outcomes This Month` for sold, slaughtered, dead, and removed counts from `PIG_MASTER` exit/status fields. After owner screenshot feedback on 2026-06-02, the outcome counts were compacted into a strip and dashboard secondary cards were changed to stop stretching to the tallest card. No new write path was added. Local JS check, focused tests, route smoke, and full unittest suite passed at 320 tests on 2026-06-02.
- Phase 9.7E closed-action cleanup and lifecycle detail readback is deployed/browser-checked for the visible action and expanded locally with real-data inspection/reconciliation: slaughter sale detail hides `Pig Exit Confirmation` for `Completed`, `Cancelled`, or `Paid` sales, the backend blocks direct confirm calls for those closed states, `/pig/<pig_id>` shows read-only lifecycle history from `PIG_MASTER`, and `/litter/<litter_id>` shows read-only lifecycle outcome counts. Local `.env` loading was added so local Flask/API inspection can use `DATABASE_URL` without affecting Render env precedence. Real sale `SALE-2026-1DE373` was inspected through the local API, linked pig `PIG-2026-C390` was confirmed already `Slaughtered` / off-farm, and closed-sale reconciliation filled `Exit_Order_ID`, normalized `Exit_Reason`, and made the displayed `Exit_Date` parse correctly. Local JS check and full unittest suite passed at 329 tests on 2026-06-02.
- Phase 9.7F litter newborn health action is live-tested complete: `POST /api/pig-weights/litter/<litter_id>/newborn-health` uses `PRODUCT_REGISTER` products and creates `MEDICAL_LOG` treatment records. Live test on 2026-06-03 with `LIT-2026-9E4A` correctly updated 10 active/on-farm piglets, skipped the dead/off-farm piglet, wrote 10 Ecomectin/Antiparasitic rows and 10 Panacur/Deworming rows, and moved the litter attention on to tag-number attention. Process correction from owner/farm: first-days newborn health is Panacur + Ecomectin only; earmarks/eartags/tag numbers belong around weaning. Next planned slices are 9.7G smart wean/tag attention timing with 35-day default weaning age, 9.7H fast pre-weaning death capture/stillborn handling with dead pig rows kept for history, and 9.7I smart return navigation. Future litter print/capture sheet alignment is parked until owner provides a sample.
- Phase 9.7G smart wean/tag attention timing is deployed and owner-verified: backend computes estimated wean date as birth/farrowing date + 35 days, starts tag/wean attention 3 days before estimated wean date, suppresses early tag-number dashboard reminders, and exposes timing fields on litter detail. Newborn health attention no longer requires earmark fields, and the newborn-health UI hides the earmark checkbox so first-days treatment is Panacur/Ecomectin only. Real-data check on 2026-06-04 for `LIT-2026-9E4A` returned estimated wean date `2026-06-22`, attention start `2026-06-19`, and no dashboard attention today. Full local unittest suite passed at 336 tests; owner deployed and confirmed it is working on 2026-06-04.
- Phase 9.7H is browser-accepted: Add Litter now uses `born_alive` for active/on-farm piglet rows and creates `stillborn_count` rows as `Dead` / `On_Farm = No` with birth-date exit date and `Exit_Reason = Stillborn`, preserving dead pig rows for history. Litter detail has a `Piglet Death Capture` preview/apply action backed by `POST /api/pig-weights/litter/<litter_id>/piglet-deaths`; it updates active/on-farm piglets to `Dead` / off-farm with event date, reason, notes, and audit fields while preserving litter/parent links. Count-based selection is allowed only while piglets are untagged/unsexed; sexed piglets require male/female counts, and tagged piglets are blocked until specific-pig selection or the individual pig lifecycle form is used. Full local unittest suite passed at 340 tests on 2026-06-04; owner browser feedback was good enough to continue.
- Phase 9.7I smart return navigation is deployed/working through the first sweep: litter piglet table links carry `return_to=/litter/<litter_id>` and `return_label=Back to Litter`; pig detail uses that safe internal return context when opened from a litter; `/litter/<litter_id>` header returns to Dashboard by default; and pig profile child pages now return to the pig profile when opened from pig detail. Owner deployed and confirmed this is working on 2026-06-04. Second return-navigation sweep is local and ready for deploy/browser check: sales dashboard rows return from sale detail to Sales Dashboard, slaughter sale ledger rows return from sale detail to Slaughter Sales, breeding analytics drill-ins return to Analytics, breeding detail litter links return to Breeding Detail, and breeding board pig/litter links return to Breeding Board.
- Phase 8E breeding board sorting/action loop is deployed and owner-verified: `/matings` now sorts action sections by operational urgency/date, closed records by newest actual farrowing/fallback date, and keeps closed/linked-litter records out of action sections. Eligible mating cards include `Add Litter`, linking to `/master/add-litter?mating_id=...`; Add Litter preselects that mating and fills the known mating details through existing form logic. Owner tested it on 2026-06-01 and confirmed it is working for now.
- Phase 8F first read-only breeding analytics slice is deployed and owner-verified: `GET /api/pig-weights/breeding-analytics` and `/breeding-analytics` summarize sow/boar mating and litter KPIs from existing `MATING_OVERVIEW` and `LITTER_OVERVIEW` with no writes. Owner confirmed it is working on 2026-06-01.
- Phase 8F drill-in/data-quality slice is local and ready for deploy/browser check: `GET /api/pig-weights/breeding-analytics/<pig_id>` and `/breeding-analytics/<pig_id>` gather the selected sow/boar's mating rows, litter rows, KPI summary, and informational data-quality flags. No recommendations or writes were added. Local JS checks, focused tests, route smoke, and full local unittest suite passed at 312 tests on 2026-06-01.
- Phase 10A operating-system map is drafted in `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`, and Phase 10.1 Supabase foundation plan is drafted in `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`.
- Phase 10.1 owner comments have been captured as guided defaults: use the existing Supabase Pro project as the foundation/staging workspace first, use plain SQL migrations in `supabase/migrations/`, keep Supabase behind the Flask backend, add `/health/database`, migrate orders/sales first, review telemetry after the first database path is proven, and keep Google Sheets visible until the database-backed path is trusted.
- Phase 10.1 first implementation slice is local: `supabase/migrations/` exists as the migration home, backend route `GET /health/database` exists, and the route is designed to be safe when `DATABASE_URL` is missing.
- Local verification passed on 2026-05-21: focused database tests passed, full local unittest suite passed at 132 tests, and `/health/database` returns safe `503` / `not_configured` before `DATABASE_URL` is added.
- Deployed verification passed on 2026-05-21: Render `DATABASE_URL` connects successfully to Supabase and `/health/database` returns `success = true`, `status = ok`, `configured = true`, `database = postgres`, and harmless UTC database time.
- Phase 10.1B baseline is local: `supabase/migrations/202605210001_foundation_migration_log.sql` creates only internal `app_private.migration_log`, and `GET /health/database/foundation` verifies it.
- Phase 10.1B local verification passed on 2026-05-21: focused database tests passed at 6 tests, full local unittest suite passed at 135 tests, and migration contract test confirms no business tables are created.
- Phase 10.1B deployed verification passed on 2026-05-21: owner ran the baseline SQL in Supabase SQL Editor and `/health/database/foundation` returned `success = true`, `status = ok`, migration ID `202605210001_foundation_migration_log`, and applied timestamp `2026-05-21T01:19:31.638474+00:00`.
- Phase 10.2 order/sales schema planning source is created in `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`.
- Owner accepted the 10.2 recommended defaults on 2026-05-21.
- Phase 10.2A empty-table migration is prepared in `supabase/migrations/202605210002_create_order_sales_tables.sql`, with backend verifier `GET /health/database/order-schema`.
- Local verification passed on 2026-05-21: focused database tests passed at 9 tests and full local unittest suite passed at 138 tests.
- Phase 10.2A deployed verification passed on 2026-05-21: owner ran the SQL migration and `/health/database/order-schema` confirmed all seven expected order/sales tables with `missing_tables = []`.
- Phase 10.2B import dry-run script is prepared in `scripts/order_sales_import_dry_run.py`; it reads Google Sheets only, writes nothing to Supabase, and reports `writes_to_supabase = false`.
- Phase 10.2B live summary-only dry-run passed on 2026-05-21 with `writes_to_supabase = false`: 26 included orders, 103 included order lines, 27 included intakes, 7 included intake items, 6 included documents, 62 included status logs, and 21 included pricing rows.
- Dry-run follow-up: `ORDER_STATUS_LOG` has 157 rows with missing parent order links and 111 rows linked to excluded test orders; investigate before import mapping.
- Owner decision: unlinked test/status-log data can stay in Sheets but should be excluded from Supabase import if it is not linked to an included main order.
- Status-log diagnostic is prepared in `scripts/order_status_log_diagnostic.py`; it reads `ORDER_MASTER` and `ORDER_STATUS_LOG` only and writes nothing.
- Phase 10.2B status-log diagnostic passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`: 62 included candidates, 157 missing-parent logs, 111 test-parent logs, and 0 missing-order-id logs.
- Import mapping rule: include only the 62 included-candidate status logs by default; exclude missing-parent/test-parent logs unless owner manually approves exceptions later.
- Phase 10.2C payload mapping is added to the dry-run script; it maps included rows to Supabase-shaped payload samples while still writing nothing to Supabase or Sheets.
- Owner rule applied: unlinked intake rows are excluded from the first import boundary.
- Phase 10.2C live payload sample report passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`: 26 orders, 103 order lines, 0 order intakes, 0 order intake items, 6 order documents, 62 order status logs, and 21 sales pricing rows mapped.
- Review finding before real import: some mapped orders are cancelled historical customer orders; owner should review whether all 26 included orders are worth importing before any actual insert.
- Owner decision update: first import should include completed real orders only, plus pricing reference data. Draft/pending/approved/cancelled/rejected history stays in Sheets unless manually approved later.
- Completed-only dry-run passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`: 3 completed orders, 53 linked order lines, 0 intakes, 0 intake items, 0 documents, 11 linked status logs, and 21 pricing rows mapped.
- Phase 10.2D shadow import script is prepared in `scripts/order_sales_shadow_import.py`; default mode is plan-only and `--apply` is required before any Supabase write.
- Phase 10.2D local verification passed on 2026-05-21: focused shadow-import/dry-run tests passed at 12 tests and full local unittest suite passed at 152 tests.
- Phase 10.2D live plan-only run passed on 2026-05-21 with `writes_to_supabase = false` and `writes_to_sheets = false`; counts matched the approved completed-only boundary.
- Phase 10.2D apply passed on 2026-05-21 after one safe rolled-back `NotNullViolation` attempt and timestamp normalization fix.
- Supabase verification confirms batch `IMPORT-20260521-COMPLETED-ORDERS-V1` contains 3 orders, 53 order lines, 0 intakes, 0 intake items, 0 documents, 11 status logs, and 21 pricing rows.
- Phase 10.2E shadow read comparison passed on 2026-05-21: `scripts/order_sales_shadow_compare.py` compared Google Sheets source mapping to Supabase batch `IMPORT-20260521-COMPLETED-ORDERS-V1` with `mismatch_count = 0`.
- Phase 10.2F read-only shadow endpoint is implemented locally: `GET /api/shadow/orders/<order_id>/compare` compares Google Sheets order detail to Supabase shadow order detail and writes nothing.
- Phase 10.2F local verification passed on 2026-05-21: focused shadow route/service tests passed at 32 tests, full local unittest suite passed at 164 tests, and local API smoke for `ORD-2026-0B29D7` returned `mismatch_count = 0`.
- Phase 10.2F deployed verification passed on 2026-05-21 for `ORD-2026-0B29D7`: response returned `success = true`, `status = ok`, `mismatch_count = 0`, and read-only flags remained false.
- No backend read/write cutover, UI change, n8n change, or Google Sheet retirement has started.
- Phase 10.2G sales transaction extension planning is captured in `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`: proposed future tables are `sales_transactions` and `sales_transaction_items` to support honest Rand values for livestock, slaughter/abattoir, and future meat/carcass sales.
- Phase 10.2H is deployed and verified: `supabase/migrations/202605210003_create_sales_transaction_tables.sql` creates empty `sales_transactions` and `sales_transaction_items` tables, and `GET /health/database/sales-transaction-schema` verifies them.
- Local verification passed on 2026-05-21: focused database tests passed at 12 tests and full local unittest suite passed at 169 tests.
- Deployed verification passed on 2026-05-21: owner ran the SQL migration and `/health/database/sales-transaction-schema` returned `success = true`, `status = ok`, migration ID `202605210003_create_sales_transaction_tables`, both expected tables found, and `missing_tables = []`.
- No backend/dashboard/order behavior changed.
- Phase 10.2I is deployed and verified: `GET /api/sales-transactions` reads Supabase sales transaction headers only, supports optional stream filtering, and reports `writes_to_sheets = false` / `writes_to_supabase = false`.
- Local verification passed on 2026-05-21: focused sales transaction/database tests passed at 17 tests, local missing-config route smoke returned safe `503`, and full local unittest suite passed at 174 tests.
- Deployed verification passed on 2026-05-21: `GET /api/sales-transactions` returned `success = true`, `status = ok`, `count = 0`, empty `sales_transactions`, and read-only source flags.
- No records, write form, dashboard Rand totals, or order automation were added.
- Phase 10.2J is implemented locally: `POST /api/sales-transactions/dry-run` validates a sales transaction payload and calculates gross, deductions, net total, item count, and pig count without connecting to Supabase.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 8 tests, local dry-run route smoke passed, and full local unittest suite passed at 177 tests.
- Deployed verification passed on 2026-05-21: dry-run slaughter payload returned `success = true`, `mode = dry_run`, `gross_total = 1200`, `deductions_total = 100`, `net_total = 1100`, and both write flags remained false.
- No real create endpoint, sale IDs, dashboard Rand totals, order automation, or pig status changes were added.
- Phase 10.2K controlled sales transaction create-flow plan is captured in `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`: first real write should be `POST /api/sales-transactions` for `Slaughter` only, with atomic Supabase inserts, duplicate pig protection, no Google Sheets writes, no dashboard Rand totals, and no pig/order status changes.
- Real slaughter workflow is captured for 10.2K: pigs are taken to `Bartelsfontein` abattoir for buyer/butcher `JC Slaghuis`; carcass weight is optional because it is not always supplied; payment is normally received about two weeks later by bank transfer/EFT; VAT handling must be treated deliberately.
- Planned slaughter status rule: use `sale_status = Confirmed` and `payment_status = Unpaid` while waiting for butcher payment, then update to `sale_status = Completed` and `payment_status = Paid` once the EFT is received.
- Pig `S10` was reported on 2026-05-21 as recently slaughtered and was marked slaughtered in Google Sheets; it later became the first real JC Slaghuis slaughter/payment close-out verification.
- Phase 10.2K1 is implemented locally: `POST /api/sales-transactions` supports `Slaughter` only, requires `created_by`, writes Supabase header/items atomically, blocks duplicate pig IDs, and writes nothing to Google Sheets.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 15 tests, local missing-config route smoke returned safe `503`, and full local unittest suite passed at 184 tests.
- Deployed 10.2K1/10.2K2 verification passed on 2026-05-21: synthetic transaction `SALE-2026-F17E16` was created for `PIG-TEST-102K2-20260521`, read back successfully, and duplicate-pig protection returned `409 duplicate_pig` on a second create attempt.
- The synthetic test transaction remains in Supabase and is clearly marked as test data. It is not linked to a real pig/order.
- At the 10.2K1/10.2K2 checkpoint, no real `S10` transaction had been written; this changed later after the create/cancel/payment path was proven.
- Phase 10.2K3 cancellation/void flow is implemented locally: `POST /api/sales-transactions/<sale_id>/cancel` requires `cancelled_by` and `cancel_reason`, marks `sale_status = Cancelled`, sets `payment_status = Cancelled`, appends an audit note, and never hard-deletes rows.
- Local verification passed on 2026-05-21: focused sales transaction tests passed at 20 tests, local missing-config cancel route smoke returned safe `503`, and full local unittest suite passed at 191 tests.
- Deployed 10.2K3 verification passed on 2026-05-21: synthetic transaction `SALE-2026-F17E16` was cancelled, duplicate release was proven by creating `SALE-2026-28EF1B` with the same synthetic pig ID, and the second synthetic transaction was also cancelled.
- Final readback shows both synthetic slaughter transactions are cancelled.
- At the 10.2K3 checkpoint, no real `S10` transaction had been written; this changed later after the form/payment path was proven.
- Phase 10.2L internal slaughter sale form is implemented locally at `/sales/slaughter`.
- The form defaults to the current real workflow values, loads active pigs, creates slaughter transactions through the verified Supabase endpoint, lists recent slaughter transactions, and can cancel non-cancelled rows.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused frontend/sales tests passed at 27 tests, local page smoke returned `200`, and full local unittest suite passed at 192 tests.
- Phase 10.2L2 payment/final amount update is implemented locally: `PATCH /api/sales-transactions/<sale_id>/payment` updates non-cancelled slaughter transaction amount, payment status, sale status, payment method, optional carcass weight, and appends an audit note.
- `/sales/slaughter` now has an `Update Payment` action for non-cancelled rows.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused sales/frontend tests passed at 23 tests, local missing-config update route smoke returned safe `503`, and full local unittest suite passed at 200 tests.
- 10.2L2 real-value test was parked by owner decision on 2026-05-21 until the real JC Slaghuis sale value was known.
- This follow-up was completed and verified on 2026-05-23; S10/payment completion is no longer owner-pending.
- Next step remains continuing with the selected Phase 10 telemetry/irrigation slices.
- Slaughter form refinement notes are captured in `NEXT_STEPS.md`: improve save-button reachability, align the bottom table with the agreed table/filter layout, plan multi-pig slaughter batches, add payment date handling, and consider estimated carcass weight from latest live weight.
- Shared page template/layout standard is captured in `NEXT_STEPS.md` so new pages stop drifting into different patterns.
- Phase 10.2L3 slaughter form UX polish is implemented locally: `/sales/slaughter` now has a top save action, transaction search, sale-status filter, payment-status filter, clear filters action, filtered transaction count, and clearer status pills.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, frontend contract tests passed at 10 tests, local page smoke returned `200`, and full local unittest suite passed at 200 tests.
- Multi-pig slaughter batch entry is still intentionally not implemented; it should be planned as 10.2L4 before changing transaction/item logic.
- Phase 10.2L4 planning is captured in `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`: use one transaction header per slaughter batch and multiple item rows for pigs.
- 10.2L4 should start with payment-date schema planning before multi-pig form implementation, because payment can happen later than slaughter.
- Phase 10.2L4A payment-date schema migration is implemented locally: `supabase/migrations/202605210004_add_sales_transaction_payment_date.sql` adds nullable `payment_date` to `sales_transactions`.
- Backend verifier `GET /health/database/sales-payment-date-schema` is implemented locally.
- Local verification passed on 2026-05-21: focused database tests passed at 15 tests, local missing-config verifier smoke returned safe `503`, and full local unittest suite passed at 203 tests.
- Phase 10.2L4A deployed verification passed on 2026-05-21: `/health/database/sales-payment-date-schema` returned `success = true`, `status = ok`, migration ID `202605210004_add_sales_transaction_payment_date`, applied timestamp `2026-05-21T15:45:04.636332+00:00`, and `payment_date_column_found = true`.
- Phase 10.2L4B backend multi-item create support is implemented locally: one sale header can carry multiple pig item rows, and duplicate `pig_id` values inside the submitted batch are blocked during validation before any database write.
- Local verification passed on 2026-05-21: focused sales transaction create/dry-run/route tests passed at 17 tests and full local unittest suite passed at 206 tests.
- Phase 10.2L4C form multi-pig selector is implemented locally: `/sales/slaughter` now supports add/remove pig rows, per-pig amount, optional carcass weight, optional pig note, calculated batch total, and duplicate-selection blocking.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused frontend/sales tests passed at 27 tests, local page smoke returned `200`, and full local unittest suite passed at 206 tests.
- Phase 10.2L4D payment update with batch total/payment date is implemented locally: payment update requires `payment_date` when marking Paid, updates header totals/payment/date/status, keeps single-pig item update behavior, and does not auto-reallocate final batch totals across multiple pig item rows.
- Local verification passed on 2026-05-21: `node --check static/js/slaughterSale.js`, focused update/route/frontend tests passed at 25 tests, local page smoke returned `200`, and full local unittest suite passed at 208 tests.
- Phase 10.2L4E deployed synthetic batch test passed on 2026-05-21: two-pig synthetic batch `SALE-2026-17736A` was created, active duplicate create was blocked with `409`, payment update to `Paid` with `payment_date = 2026-05-21` succeeded, the batch was cancelled, reuse batch `SALE-2026-0C9DE0` proved duplicate-pig release, and the reuse batch was cancelled.
- Deployed `/sales/slaughter` page smoke passed and included the multi-pig row container plus batch total UI.
- Synthetic test pig IDs were `PIG-TEST-L4E-A-20260521180640` and `PIG-TEST-L4E-B-20260521180640`; both synthetic transactions are cancelled.
- Phase 10.2L4 is closed after deployed synthetic verification; manual UI owner smoke is optional, not a blocker.
- S10 / real JC Slaghuis payment completion is now verified and closed for now. Owner entered the real payment/final amount on 2026-05-23 after backend deploy. Supabase shows sale `SALE-2026-1DE373` for pig `PIG-2026-C390` / tag `S10`, buyer `JC Slaghuis`, destination `Bartelsfontein`, carcass weight `68 kg`, final amount `R2892.94`, `payment_status = Paid`, `payment_method = EFT`, `payment_date = 2026-05-23`, and `sale_status = Completed`. Focused sales transaction tests passed at 35 tests.
- Phase 10.3 telemetry review is selected as the next Phase 10 slice.
- Phase 10.3 working source is created in `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`.
- 10.3 scope is planning-first: inventory weather, Sunsynk, forecast, irrigation, and alert data; design compact backend read models for Oom Sakkie and dashboard use; keep working weather stable; and fix the slow Sunsynk path by moving toward backend/Supabase prepared payloads instead of more agent-over-sheet loops.
- Initial repo inventory found no backend telemetry modules or local telemetry ingestion scripts in this repo; current telemetry knowledge is in n8n workflow exports/docs, so external logger/cron/script locations still need owner confirmation.
- External source folders have been imported and filed under `external_sources/`: Sunsynk logger, local weather station logger, forecast logger, and non-telemetry landing-page source. One forecast `.env` file is present but ignored by git.
- 10.3A partial inventory now captures each logger's env vars, external API, sheet write target, and likely role.
- Owner confirmed telemetry loggers run as Render cron services; irrigation appears to be n8n-run.
- Owner confirmed production spreadsheets for Sunsynk, Weather, and Irrigation.
- Local Google Sheets inventory is blocked until the three telemetry spreadsheets are shared with service account `amadeuspigtrackersystem@amadeus-farm-weather-bot.iam.gserviceaccount.com`.
- Retention/rollup direction is captured: current state plus short raw retention, then daily/monthly/yearly rollups for long-term useful data.
- Service account access is now confirmed for the three telemetry sheets.
- Weather and irrigation tab/header/formula inventory succeeded.
- Sunsynk metadata inventory succeeded, but values reads timed out even on tiny ranges, confirming the current Sunsynk sheet is not a good live answer source for Oom Sakkie.
- 10.3A conclusion: keep weather stable for now, treat irrigation as a later hardware-control/audit design, and prioritize Sunsynk current-state backend/Supabase read model first.
- 10.3B Sunsynk current-state read model is planned: first endpoint should be `GET /api/telemetry/power/current`, returning source freshness, current battery/solar/load/grid/generator state, deterministic flags, backend-prepared summary wording, and explicit stale/unavailable behavior.
- Owner agreed the 10.3B payload direction.
- 10.3C telemetry schema proposal is documented: first migration should be power-first with `telemetry_sources`, `power_readings_5min`, `power_latest_state`, and `telemetry_alerts`; hourly/daily/monthly/yearly rollups wait until energy calculation rules are confirmed.
- Owner agreed to implement 10.3C.
- Phase 10.3C first telemetry power schema migration is implemented locally: `supabase/migrations/202605210005_create_telemetry_power_tables.sql`.
- Backend verifier `GET /health/database/telemetry-power-schema` is implemented locally.
- Migration creates `telemetry_sources`, `power_readings_5min`, `power_latest_state`, and `telemetry_alerts`, and seeds `sunsynk-main-inverter`; it imports no telemetry readings, changes no Render logger, and changes no n8n workflows.
- Local verification passed on 2026-05-21: focused database tests passed at 18 tests, local missing-config verifier smoke returned safe `503`, and full local unittest suite passed at 211 tests.
- Phase 10.3C deployed verification passed on 2026-05-21: `/health/database/telemetry-power-schema` returned `success = true`, `status = ok`, migration ID `202605210005_create_telemetry_power_tables`, all four expected tables found, `missing_tables = []`, and `sunsynk_source.source_id = sunsynk-main-inverter` with `stale_after_minutes = 15`.
- Future Supabase migrations can be run directly from the local workspace when `DATABASE_URL` is available locally and network/database command approval is granted; still inspect SQL first, run exactly one migration file, then verify through the matching backend health endpoint.
- 10.3D ingestion decision is documented: existing Render Sunsynk logger should call the Flask backend, not write directly to Supabase. Backend owns validation, raw/latest writes, summary flags, and Oom Sakkie read model.
- 10.3E backend endpoints are implemented locally: `POST /api/telemetry/power/ingest` protected by `TELEMETRY_INGEST_API_KEY`, and `GET /api/telemetry/power/current` for Oom Sakkie/dashboard current-state reads.
- Local verification passed on 2026-05-21: focused telemetry tests passed at 8 tests, local route smokes returned safe config failures, and full local unittest suite passed at 219 tests.
- 10.3D/10.3E deployed verification passed on 2026-05-21: synthetic ingest returned `success = true`, `status = ok`, `source_id = sunsynk-main-inverter`, `reading_id = PWR-FEC6256BECB7`, and `source.writes_to_supabase = true`.
- Deployed current-state readback passed: `/api/telemetry/power/current` returned battery `82%`, battery state `charging`, solar `3120 W`, load `1240 W`, grid state `not_using_grid`, generator `off`, deterministic flags, and stale summary because the synthetic timestamp was intentionally old.
- Security note: rotate `TELEMETRY_INGEST_API_KEY` before wiring the real Render Sunsynk logger if the current test key was pasted into chat or logs.
- 10.3F Sunsynk logger update is implemented locally in `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/main.py`.
- Logger now posts to backend ingest when `AMADEUS_BACKEND_URL` and `TELEMETRY_INGEST_API_KEY` are set, while keeping Google Sheets as a transition mirror unless `GOOGLE_SHEETS_ENABLED=false`.
- Logger README added with required Render cron env vars.
- First Render cron recovery test failed in the Google Sheets mirror path with `gspread` 404. The deployed current-state endpoint still showed the old synthetic test reading, so the real logger had not yet refreshed Supabase.
- Logger is now hardened locally so a successful backend ingest is not failed by a Google Sheets mirror error. Recommended next recovery test is to deploy the hardened logger with `GOOGLE_SHEETS_ENABLED=false`, then verify `/api/telemetry/power/current` returns a fresh real reading.
- Render cron source has been moved to the main `amadeus-pig-tracking-system` repo with root directory `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger`; a trailing-space root directory issue was corrected.
- Phase 10.3F deployed verification passed on 2026-05-22: Render cron printed `backend_ingest_enabled = true`, `backend_ingest_success = true`, reading ID `PWR-49F0F62E4F21`, `google_sheets_written = true`, and timestamp `2026-05-22T00:28:20+02:00`.
- `/api/telemetry/power/current` read back the real fresh state with `data_age_minutes = 0`, `is_stale = false`, battery `47%`, battery state `discharging`, load `872 W`, no solar, no grid, and no generator.
- Local syntax verification passed with `python -m py_compile`.
- Next step is updating Oom Sakkie `2.2` to use the backend current power endpoint instead of Google Sheets.
- 10.3G local workflow update is prepared: `2.2 - Amadeus Sunsynk Sub-Agent` now calls `GET /api/telemetry/power/current` and formats the backend payload directly, with no LangChain agent loop and no Sunsynk Google Sheets tools.
- `2.0 - OOM SAKKIE` `Sunsynk_Info_Tool` description now describes the backend/Supabase current-power tool and limits this slice to current/live power state.
- Local JSON parse verification passed for both updated workflow exports.
- 10.3G live verification passed on 2026-05-22 after importing `2.2` and `2.0` into n8n.
- Telegram test `What's the power like now?` returned quickly with current backend/Supabase data: battery `46%` discharging, solar `0.0 kW`, load `1.0 kW`, grid not using grid `0 W`, generator off `0 W`, latest reading `22 May 2026, 00:40`, and data age `4 minutes`.
- This confirms Oom Sakkie current power questions no longer depend on slow Sunsynk Google Sheets reads.
- Next selected slice was the recent power profile endpoint.
- 10.3H local backend slice is prepared: `GET /api/telemetry/power/recent?hours=24` summarizes recent Supabase `power_readings_5min` rows without claiming kWh/cost totals.
- The recent-power endpoint returns sample-based battery range, average/max solar/load, grid/generator active sample counts, approximate active minutes, hourly buckets, and coverage percentage.
- Focused telemetry/workflow tests pass at 11 tests, and the full local test suite passes at 221 tests.
- First deployed check returned `success = true` with expected sections, but it still included the old synthetic test row inside the 24-hour window.
- A local follow-up patch now excludes rows with `raw_payload is null` so synthetic/manual test rows do not skew the recent profile.
- Focused telemetry/workflow tests still pass at 11 tests after the exclusion patch.
- 10.3H deployed verification passed after redeploy: `/api/telemetry/power/recent?hours=24` returned `success = true`, 24 real cron rows, first reading `2026-05-21T22:28:20+00:00`, last reading `2026-05-22T00:20:21+00:00`, battery range `42%` to `47%`, average load `0.9 kW`, maximum solar `0.0 kW`, and no grid/generator activity.
- The synthetic `82%` / `3120 W` row is no longer present in the live response.
- 10.3I live verification passed on 2026-05-22 after importing updated `2.2` and `2.0`.
- Oom Sakkie now answers current/live power questions from `/api/telemetry/power/current` and recent/last-24h/trend questions from `/api/telemetry/power/recent?hours=24`.
- Live Telegram checks passed for current power, last-24h profile, last-night grid use, and solar-total limitation wording.
- `2.2` remains deterministic with no LangChain agent loop and no Google Sheets tool reads. kWh, cost, import, and export total questions return the sample-based profile with a clear limitation instead of invented totals.
- Minor polish note: recent-profile answers can repeat the sample-based limitation because the backend operator notes and workflow formatter both include it. This is harmless and can be cleaned up in a later wording pass.
- 10.3J weather/forecast alignment is now in planning.
- Current `2.1 - Amadeus Weather Sub-Agent` is sheet-backed and uses an LLM router plus LLM answer formatter. It reads `LLM_Latest_Reading`, `Forecast_10Day_Current`, and `Daily_Pivot`.
- Current `2.1.1 - Amadeus Forecast Tool` is a standalone Open-Meteo utility, but the normal `2.1` Oom Sakkie weather path does not appear to call it.
- Recommended direction is the same proven Sunsynk pattern: define backend weather/forecast payload contracts first, then add Supabase schema and ingest/read endpoints, then update `2.1` only after direct backend checks pass.
- 10.3J1 weather/forecast read-model contract is drafted in `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`.
- First build contract includes `/api/telemetry/weather/current` and `/api/telemetry/weather/forecast?days=3`.
- `/api/telemetry/weather/today` is planned as a follow-up unless it is very low-risk to add after current/forecast are proven.
- The contract defines success/unavailable payloads, units, freshness, deterministic weather/forecast flags, and backend summary wording.
- 10.3J2 is implemented and the Supabase schema has been applied.
- Local migration `supabase/migrations/202605220001_create_telemetry_weather_tables.sql` creates `weather_readings`, `weather_latest_state`, and `weather_forecast_snapshots`, and inserts telemetry sources for `weather-station-main` and `open-meteo-forecast-main`.
- Backend endpoints are prepared for weather current read, forecast read, weather ingest, and forecast ingest.
- Health endpoint `/health/database/telemetry-weather-schema` is prepared.
- Local validation passed on 2026-05-22: syntax compile passed, focused weather/database checks passed, and broader telemetry/database/workflow tests passed at 53 tests.
- The migration was applied directly to Supabase on 2026-05-22 and schema health verified `success = true`, `missing_tables = []`, with both weather/forecast sources present.
- Direct local Supabase read checks returned clean unavailable responses for `/api/telemetry/weather/current` and `/api/telemetry/weather/forecast?days=3` before logger ingest.
- Synthetic local ingest is blocked until `TELEMETRY_INGEST_API_KEY` is configured in the local `.env`; Render already has the key for deployed endpoint testing.
- Deployed backend verification on 2026-05-22 passed for `/health/database/telemetry-weather-schema`, `/api/telemetry/weather/current`, and `/api/telemetry/weather/forecast?days=3`; both read endpoints return clean unavailable responses before logger ingest.
- Synthetic deployed ingest is blocked because the available test key returned `401 unauthorized`; use the current Render `TELEMETRY_INGEST_API_KEY` value for the next ingest/readback check.
- Synthetic deployed ingest/readback passed on 2026-05-22 after confirming the current ingest key.
- `POST /api/telemetry/weather/ingest` wrote reading `WTH-5D66D385B9F5` to Supabase and `/api/telemetry/weather/current` read it back with temperature `14.2 C`, humidity `86%`, wind `5.4 km/h`, rain today `0.4 mm`, `success = true`, and source `weather-station-main`.
- `POST /api/telemetry/weather/forecast/ingest` wrote 3 forecast rows and `/api/telemetry/weather/forecast?days=3` read them back with `returned_days = 3`, rain expected on 2 days, and source `open-meteo-forecast-main`.
- The current weather/forecast values in Supabase are synthetic test values until the real Render weather and forecast loggers overwrite them.
- First owner weather cron run still showed the old Sheets-only output (`Logged Current_Conditions...`), confirming the logger code had not yet been updated for backend ingest.
- Local logger updates are prepared: both weather and forecast Render cron scripts now support `BACKEND_INGEST_ENABLED=true`, keep `GOOGLE_SHEETS_ENABLED=true` as a mirror, post to the backend ingest endpoints, and print JSON results including `backend_ingest_success`.
- 10.3J3 logger verification passed on 2026-05-22.
- `/api/telemetry/weather/current` now reads fresh real weather-station data from Supabase: temperature `14 C`, humidity `96%`, wind `8 km/h`, rain today `0 mm`, data age `0`, source `weather-station-main`.
- `/api/telemetry/weather/forecast?days=3` now reads fresh real Open-Meteo forecast data from Supabase: returned 3 days, rain possible on 1 day, data age `0`, source `open-meteo-forecast-main`.
- This confirms the real weather and forecast Render cron loggers have overwritten the synthetic test values.
- 10.3J4 local workflow simplification is prepared.
- `2.1 - Amadeus Weather Sub-Agent` now has only deterministic backend-read nodes: trigger, route weather question, HTTP read, format answer, and sticky note.
- The old `2.1` Google Sheets and LLM nodes are intentionally removed from the export: `Weather Router (JSON Plan)`, `Weather Answer LLM (JSON only)`, `Precheck - Latest Station Row`, `Read Forecast_10Day_Current`, and `Read Daily_Pivot`.
- `2.0 - OOM SAKKIE` `Weather_Info_Tool` description now identifies `2.1` as a backend/Supabase current-weather and forecast worker.
- Workflow contract tests pass at 15 tests after the local workflow export update.
- 10.3J4 live verification passed on 2026-05-22 after importing updated `2.1` and `2.0`.
- Telegram test `What is the weather like now?` returned current backend weather: temperature `14 C`, humidity `96%`, wind `4 km/h`, gusts `4 km/h`, rain now `0 mm/h`, rain today `0 mm`, pressure `1013.9 hPa`, and latest reading age `0 minutes`.
- Telegram test `What is the weather forecast for the next few days?` returned the 3-day backend forecast for 22-24 May 2026, including rain possible on 1 day and forecast age `1 minute`.
- Oom Sakkie did not mention tools, workflows, Google Sheets, or Supabase in the tested answers.
- Owner selected the next telemetry order: 1) weather today summary, 2) weather alert alignment, 3) irrigation/audit planning.
- 10.3K local weather today summary is prepared.
- Added read-only `GET /api/telemetry/weather/today`, with optional `date=YYYY-MM-DD`.
- The endpoint summarizes existing Supabase `weather_readings` for the selected local day: reading count, first/last reading, coverage estimate, min/max/average temperature, average humidity, max wind/gust, rain total, max rain rate, flags, and operator notes.
- It excludes synthetic test rows where `raw_payload.test = true`, so the earlier synthetic weather ingest does not skew today summaries.
- Local live Supabase readback returned real-only data for 2026-05-22: 5 readings, first reading `2026-05-22T02:49:30+00:00`, last reading `2026-05-22T03:04:54+00:00`, temperature `14 C`, rain total `0 mm`, max wind `9 km/h`, coverage `8.1%`.
- Focused and broader telemetry/database/workflow tests pass at 55 tests.
- 10.3K deployed verification passed on 2026-05-22.
- `/api/telemetry/weather/today` returned `success = true`, date `2026-05-22`, 25 real readings, coverage `30.5%`, first reading `2026-05-22T02:49:30+00:00`, last reading `2026-05-22T04:45:06+00:00`, min/max/avg temperature `14 C` / `15 C` / `14.24 C`, rain total `0 mm`, max wind `9 km/h`, and max gust `10 km/h`.
- Explicit dated check `/api/telemetry/weather/today?date=2026-05-22` returned the same result.
- The old synthetic `0.4 mm` rain row is excluded.
- `2.1` local workflow update is prepared so today/daily/rain-today weather questions route to `/api/telemetry/weather/today`.
- First live Telegram check for `What happened with the weather today?` still returned the current-weather branch. The local workflow files were hardened: `2.0` now passes the exact Telegram message into `2.1`, and `2.1` now checks additional input fields plus `what happened ... today` wording.
- Workflow/weather tests pass at 26 tests after the route update.
- 10.3K live verification passed on 2026-05-22 after importing the hardened `2.0` and `2.1` workflows.
- Telegram test `What happened with the weather today?` returned the today-summary branch: 30 readings, 34.5% coverage, temperature `14 C` to `15 C`, average `14.4 C`, average humidity `94.6%`, rain total `0 mm`, max rain rate `0 mm/h`, max wind `9 km/h`, max gust `10 km/h`, and measurement window `22 May 2026, 04:49` to `07:10`.
- 10.3L weather alert alignment is planned.
- Owner agreed alerts should use the backend/Supabase approach rather than the old Sheets-first alert workflows.
- Backend should own alert rules, cooldowns, duplicate prevention, and alert history in `telemetry_alerts`.
- n8n should later become a thin scheduled caller and Telegram delivery layer.
- Existing `ALERT - Local Weather Station` and `ALERT - Weather Forecast` remain documented and should not be activated as the source of truth during this rebuild.
- Initial alert defaults are documented for station stale, rain, heavy rain, sustained wind, gusts, temperature, forecast rain, and forecast wind.
- First safe recipient should be Charl only.
- Default quiet hours are `21:00` to `06:00` Africa/Johannesburg, with `HIGH` current-condition alerts allowed through.
- 10.3L2 backend evaluator is implemented locally.
- Added protected `POST /api/telemetry/weather/alerts/evaluate`.
- Evaluator supports dry-run mode, returns `sendable_alerts`, `held_alerts`, and `suppressed_alerts`, and writes only sendable alerts in apply mode.
- It does not send Telegram messages.
- Focused weather tests pass at 13 tests; telemetry/database/workflow suite passes at 57 tests.
- Real Supabase dry-run returned `success = true`, `mode = dry_run`, and zero current alert candidates under normal weather conditions.
- 10.3L2 deployed dry-run verification passed on 2026-05-22.
- Production `POST /api/telemetry/weather/alerts/evaluate` with `{"dry_run": true}` returned `success = true`, `status = ok`, `mode = dry_run`, zero candidates, zero sendable/held/suppressed alerts, and `writes_to_supabase = false`.
- Backend-only audit test path is prepared locally.
- `POST /api/telemetry/weather/alerts/evaluate` supports `{"include_test_alert": true}` to create a clearly marked `BACKEND_AUDIT_TEST` candidate.
- In apply mode this writes one backend audit row to `telemetry_alerts`; it does not send Telegram.
- Focused weather tests pass at 14 tests.
- 10.3L2 backend audit apply verification passed on 2026-05-22.
- Production audit dry-run with `{"dry_run": true, "include_test_alert": true}` returned one `BACKEND_AUDIT_TEST` candidate and `writes_to_supabase = false`.
- Production audit apply with `{"include_test_alert": true}` wrote alert `ALT-F20D2245949B`.
- Supabase verification confirmed `ALT-F20D2245949B` exists with `area = weather`, `alert_type = BACKEND_AUDIT_TEST`, `severity = info`, `status = Open`, `details.test = true`, and `details.safe_to_ignore = true`.
- No Telegram message was sent.
- 10.3L4 n8n weather alert delivery is planned.
- New workflow should be `ALERT - Weather Backend Delivery`.
- It must call the backend evaluator and treat backend as the only source of truth.
- It must ignore `BACKEND_AUDIT_TEST` and any alert with `details.test = true`.
- First recipient scope is Charl only.
- Legacy Sheets-first alert workflows remain inactive/documented.
- 10.3L4 local workflow export is built:
  - `docs/04-n8n/workflows/ALERT - Weather Backend Delivery/workflow.json`
  - `docs/04-n8n/workflows/ALERT - Weather Backend Delivery/README.md`
- The workflow is inactive by default.
- It calls `POST /api/telemetry/weather/alerts/evaluate`.
- n8n Cloud denied `$env` access in the HTTP node, so the workflow now uses a manually configured `X-Amadeus-Telemetry-Key` header value matching Render's `TELEMETRY_INGEST_API_KEY`.
- It filters out dry-run responses, `BACKEND_AUDIT_TEST`, and `details.test = true`.
- It sends through `Telegram - Oom Sakkie` to Charl-only chat ID `5721652188` for the first trial.
- Workflow contract tests pass at 16 tests.
- Manual n8n dry-run/audit-test verification passed on 2026-05-23: the backend returned one `BACKEND_AUDIT_TEST` candidate in dry-run mode, `Code - Extract Sendable Alerts` emitted zero items, and no Telegram delivery occurred.
- Scheduled dry-run verification passed on 2026-05-23: execution `47520` ran from the schedule, backend returned `success = true`, `mode = dry_run`, zero candidates/sendable/held/suppressed alerts, and `Code - Extract Sendable Alerts` output zero items, so Telegram delivery was not reached.
- Live scheduled verification passed on 2026-05-23: workflow was active with `dryRun = false` and `includeTestAlert = false`; execution `47527` ran from the schedule, backend returned `success = true`, `mode = apply`, zero candidates/sendable/held/suppressed alerts, `source.writes_to_supabase = true`, and no written alert IDs; `Code - Extract Sendable Alerts` output zero items, so Telegram delivery was not reached because there were no real alerts.
- Weather backend alert delivery is live-verified. `ALERT - Weather Backend Delivery` remains active as the only live weather alert delivery workflow.
- Legacy weather alert cleanup is complete: `ALERT - Local Weather Station` and `ALERT - Weather Forecast` are inactive/archived in n8n and their repo exports have been removed.
- 10.3N Sunsynk/power alert backend alignment is live-verified: `POST /api/telemetry/power/alerts/evaluate` is implemented, backend rules/cooldowns/quiet-hours handling now cover not logging, battery low/medium/high, grid active, generator active, and `POWER_BACKEND_AUDIT_TEST`, and `ALERT - Power Backend Delivery` has been imported, manually dry-run tested, and live-tested.
- Manual n8n dry-run and audit dry-run executions passed on 2026-05-23: the backend returned real power candidates, `POWER_BACKEND_AUDIT_TEST` was filtered out, `Code - Extract Sendable Alerts` emitted zero items while `dryRun = true`, and no Telegram delivery occurred.
- Live n8n execution `47565` passed on 2026-05-23: backend mode was `apply`, `POWER_BATTERY_LOW` was written to Supabase as `ALT-C758569F3D95`, Telegram delivery succeeded, and `POWER_GRID_ACTIVE` was held by quiet hours.
- Owner made `ALERT - Power Backend Delivery` live and removed the old `ALERT - Sunsynk` workflow from n8n. Repo cleanup also removed the legacy `docs/04-n8n/workflows/ALERT - Sunsynk/` export so it does not get reintroduced by mistake.
- Owner planning notes are captured in `SUPABASE_TELEMETRY_PLAN.md`: future Sunsynk cost/value reporting should use `R9.10/kWh` as a planning default; n8n remains a thin integration layer for now; human alerts must be separated from automation triggers for irrigation/pumps/power safety.
- 10.3O irrigation inventory/control-boundary planning has started. Current export shows `2.3.1 - Build Daily Irrigation Plan` is active and writes irrigation plan/state/log rows, while `2.3.2 - Run Irrigation Controller` is inactive but contains direct IFTTT start/stop HTTP nodes that can control real hardware if activated.
- Current irrigation guardrail: do not activate `2.3.2`, do not edit IFTTT start/stop nodes, do not add Oom Sakkie irrigation start/stop commands, and do not build backend hardware-control endpoints until the command/audit/safety model is agreed.
- Owner clarified the long-term irrigation goal: read-only backend status first, then a smart adaptive irrigation system that uses zone configuration, crop/planting context, season runtimes, priority, forecast, current weather, and power state to build/pause/reschedule plans and inform the owner when zones run, stop, change, or get reprioritized.
- Owner added that irrigation is a core operating system and must support future devices/triggers. Fertilizer injection and fertilizer tank mixing valves should be modeled separately from normal irrigation zones, and future tank full/empty states should become structured sensor inputs rather than ad hoc workflow logic.
- 10.3P read-only irrigation status endpoint is deployed and verified. `GET /api/telemetry/irrigation/status` reads the existing irrigation sheet, returns `mode = read_only`, disables all hardware-control flags, and verified today's plan from `Amadeus_Irrigation_Logs` without writing to Sheets or Supabase. A next-zone clarity patch is prepared: the endpoint keeps `STATE.next_zone_id` as the displayed next zone when present, but also returns computed priority/water-score next-zone fields and a mismatch flag for cautious Oom Sakkie wording.
- 10.3Q is live-verified. `2.3.3 - Irrigation Status Tool` is active as the read-only Oom Sakkie irrigation status worker, updated `2.0` has `Irrigation_Info_Tool`, and owner confirmed status and control-style tests work. `2.3.2 - Run Irrigation Controller` remains inactive and must not execute during Oom Sakkie status tests.
- 10.3R irrigation Supabase data model is deployed and verified. Render `/health/database/irrigation-schema` returned `success = true`, `status = ok`, `missing_tables = []`, all eight expected irrigation tables, and source row `irrigation-controller-main`. No data import, dashboard, Oom Sakkie control, IFTTT call, or `2.3.2` change has been made.
- 10.3S irrigation sheet-to-Supabase dry-run is complete. `scripts/irrigation_import_dry_run.py` read `Amadeus_Irrigation_Logs` and wrote nothing to Supabase or Google Sheets. Real dry-run mapped 2 zones, 73 daily plans, 146 plan items, 77 events, and 1 state snapshot, with no duplicate zone IDs and no link issues. Next decision is whether to build a controlled apply/import path or first refine state snapshots, auxiliary devices, and tank sensor modeling.
- Owner decision: irrigation `STATE` is the latest truth, not an append-only state history. The controlled import path should upsert `irrigation_state_snapshots` by `state_snapshot_id` and use `irrigation_events`, daily plans, and plan items for historical questions. Detailed state history can be added later as a separate model only if needed.
- 10.3T controlled irrigation Supabase import is applied and verified. Import batch `IMPORT-20260523-IRRIGATION-SHEET-V1` contains 2 zones, 73 daily plans, 146 plan items, 77 events, and 1 latest-state row. Verification confirmed `IRRSTATE-MAIN` is the only state row, with `current_status = IDLE`, `current_zone_id = C12345`, and `next_zone_id = C12345`. No Google Sheets writes, n8n changes, hardware commands, IFTTT calls, or `2.3.2` activation occurred.
- Owner clarification: irrigation's operational plan should be today's active plan only, refreshed/rebuilt daily. Historical imported plan rows can stay in Supabase for audit/review, but the current status/dashboard read path must not combine historical plans into the live plan view.
- 10.3U Supabase-backed irrigation status read path is locally ready. The existing endpoint can now read from Supabase when `IRRIGATION_STATUS_SOURCE=supabase`, or try Supabase then fall back to Sheets when `IRRIGATION_STATUS_SOURCE=auto`. Default remains `google_sheets` until the daily planner/sync path writes refreshed plans into Supabase. Local live-style Supabase check returned today's selected plan `IRRPLAN-2026-05-23` and read-only safety flags.
- 10.3V irrigation daily sync is applied locally for `2026-05-23`. `scripts/irrigation_daily_sync.py` plan-only mode scoped the sync to 1 daily plan, 2 plan items, 1 latest-state row, 1 event, and 2 zones; `--apply` wrote batch `SYNC-IRRIGATION-2026-05-23` to Supabase. Supabase-backed status then returned `IRRPLAN-2026-05-23` with only today's two plan items and read-only safety flags. This is still manual; no scheduled sync has been created.
- 10.3U/V deploy default-source check passed. Render `/api/telemetry/irrigation/status?date=2026-05-23` still uses `source = google_sheets`, returns today's two planned zones, returns latest `STATE`, and keeps `read_only = true`, `can_control = false`, and `hardware_commands_enabled = false`. `IRRIGATION_STATUS_SOURCE=auto` has not yet been enabled on Render.
- 10.3U/V auto-source check passed after setting `IRRIGATION_STATUS_SOURCE=auto` on Render. Deployed response returned `source = supabase`, `today.daily_plan_id = IRRPLAN-2026-05-23`, today's two current plan rows only, and read-only safety flags. A local polish fix dedupes repeated recent events caused by historical import plus daily sync containing the same logical `PLAN_CREATED` event; redeploy needed for that display cleanup.
- 10.3U/V is live-verified after redeploy. Supabase source remains active, duplicate recent event display is cleaned up, and safety flags remain `read_only = true`, `can_control = false`, and `hardware_commands_enabled = false`.
- 10.3W telemetry rollup planning has started. Recommended defaults are now captured: keep power/weather raw readings for at least 90 days initially, keep irrigation events/plans long-term, keep daily/monthly/yearly rollups permanently, mark kWh/Rand values as estimated unless confirmed Sunsynk energy counters are available, and do not delete old telemetry Sheets until backup/import/compare checks are accepted.
- Owner accepted 10.3W defaults: 90-day raw retention for power/weather, delete old telemetry Sheets after backup/import/compare acceptance rather than leaving permanent clutter, include fertilizer/tank placeholders in irrigation rollups now, and keep `R9.10/kWh` as the planning tariff until a tariff table exists.
- 10.3W2 is applied and locally verified. Migration `202605230003_create_telemetry_rollup_tables` created empty daily/monthly/yearly rollup tables for power, weather, and irrigation; `/health/database/telemetry-rollup-schema` returned `success = true`, `status = ok`, all nine expected tables, and `missing_tables = []`. No rollup generation, schedule, dashboard, sheet deletion, or irrigation control path has been added.
- 10.3W3 plan-only daily rollup generator is ready. `scripts/telemetry_daily_rollup_plan.py --date 2026-05-23` returned one candidate row each for power, weather, and irrigation daily rollups with `writes_to_supabase = false`; power/weather coverage was `40.97%` because the day was still in progress, and irrigation event count deduped to `1`. Tests passed at 64 telemetry/database tests.
- 10.3W4 one-date daily rollup apply is complete for `2026-05-23`. Supabase now has one daily power, weather, and irrigation rollup row for that date. The apply was manual and unscheduled; no monthly/yearly rollup, dashboard, sheet cleanup, or hardware-control path was added. Because the date was still in progress, power/weather coverage is low and should be treated as a write-path test rather than a final closed-day summary.
- 10.3W5 read-only daily rollup compare endpoint is ready. `GET /api/telemetry/rollups/daily?date=2026-05-23` returns stored daily rollups plus current raw/source counts and correctly flags current-day drift because new power/weather samples arrived after the test rollup apply. This confirms the app can inspect rollup quality before scheduling.
- 10.3W6 after-day-close guard is ready. `scripts/telemetry_daily_rollup_plan.py --apply` now refuses today/future ZA dates unless `--allow-partial` is explicitly supplied. Normal current-day apply returned `day_not_closed`; explicit partial apply refreshed the test rows, and the compare endpoint then showed matching current/stored sample counts while still warning low coverage.
- 10.3W7 schedule command is verified. Owner selected `00:15` Africa/Johannesburg. Script now supports `--previous-day`; command `python scripts/telemetry_daily_rollup_plan.py --previous-day --apply` successfully applied `2026-05-22` without partial override, and compare endpoint confirmed power/weather stored counts match raw counts with power quality `complete` and weather quality `usable`.
- Backend containing the 10.3W7 rollup script was deployed by owner on 2026-05-25. Render cron `amadeus-telemetry-daily-rollups` was created on 2026-05-25 and built successfully. It runs `python scripts/telemetry_daily_rollup_plan.py --previous-day --apply` at `10:15 PM UTC` / `00:15 Africa/Johannesburg`. No `render.yaml` / Render Blueprint exists in this repo, so the cron is dashboard-managed.
- 10.3W8 first scheduled Render cron run is verified on 2026-05-26. `/api/telemetry/rollups/daily?date=2026-05-25` returned `success = true`, `status = ok`, and all three rollups found. Power stored/current samples matched at `288/288` with `100%` coverage and quality `complete`; weather matched at `287/288` with `99.65%` coverage and quality `complete`; irrigation matched with `0` events and `0` plan items. Power kWh/Rand values remain estimated until confirmed Sunsynk energy counters are available.
- Phase 10 farm home/dashboard first local slice is ready and owner-reviewed on 2026-05-26. The `/` dashboard now uses the wide `ops-shell` / `ops-dashboard` operational template rather than the narrow centered `page-card` layout. It is read-only and uses existing APIs for weather, forecast, power, irrigation, daily rollups, herd/litter attention, sales exits, and order attention. Local focused tests and route smoke passed. Owner accepted the layout direction after stale local port `5000` processes were replaced and telemetry data loaded correctly. Minor visual polish remains before deploy, especially tight metric wrapping.
- Dashboard polish was applied locally on 2026-05-26: compact metric tiles auto-fit, values no longer split mid-word, machine labels are shown as readable labels, and the dashboard script cache-buster was refreshed. Local port `5000` was restarted and confirmed to serve the updated dashboard plus JSON telemetry endpoints.
- Phase 10 farm home/dashboard live verification passed on 2026-05-26. Owner confirmed the live home page is good after deploy.
- Dashboard slaughter sale count/value source is live-verified on 2026-05-26. The dashboard summary now reads monthly non-cancelled Supabase `sales_transactions` and exposes count plus net Rand value by stream; the home dashboard displays Livestock, Slaughter, and Meat as `count / value`. Old pig-exit monthly counts remain available as separate audit fields. Owner confirmed the live dashboard now displays the slaughter sale value.
- `/sales-dashboard` sales overview/reporting is deployed and awaiting owner browser acceptance: it now provides period/month/year/custom filters, stream filters, sales totals across livestock/slaughter/meat, a clickable transaction ledger, and keeps stock availability as a secondary section.
- Supabase Security Advisor warning received on 2026-05-27 for `rls_disabled_in_public`. RLS hardening migration `supabase/migrations/202605270001_enable_rls_on_public_tables.sql` was applied by owner and verified on 2026-05-30. Security Advisor now shows `0 errors` and `0 warnings`; remaining `RLS Enabled No Policy` rows are informational and expected because backend-owned `DATABASE_URL` access remains the intended path and browser/Data API access should stay closed by default.
- New Phase 10 follow-up notes are captured in `NEXT_STEPS.md`: herd tile total/breakdown audit, Telegram digest/reminders for farm attention, practical alert timing/rain-summary rules, alert message formatting polish, weather/solar dashboard symbols, future task/reminder/project management, and possible Windy weather-station integration research.
- Herd dashboard count audit is deployed and browser-verified: backend herd counts reconciled to `103` on-farm pigs once `Gilts`, `Piglets`, and `Growers` were included in the visible tile.
- Farm attention Telegram digest backend slice is deployed and smoke-verified: `GET /api/reports/farm-attention-summary` combines existing order attention and litter attention into a read-only digest contract for n8n. Production returned one current item, `LIT-2026-8A0F` for piglet tag numbers, with no order attention items. It sends no Telegram messages and writes nothing to Supabase or Google Sheets.
- Farm attention digest workflow is live-verified: `ALERT - Farm Attention Digest` calls the backend summary endpoint, filters empty digests, suppresses repeated content with workflow static data for non-manual executions, and sends only to Charl. Manual executions `49137` and `49138` sent the expected digest for `LIT-2026-8A0F`; manual execution `49136` proved the no-output gate; scheduled execution `49154` stopped at `Code - Extract Sendable Digest` with zero output and no Telegram send.
- `/sales/slaughter` payment update UX is locally browser-checked: the awkward browser-prompt update path is replaced with an in-page update panel for final amount, payment status/date, payment method, sale status, carcass weight, updated-by, and update note. Backend payment rules are unchanged.
- `/sales/slaughter` wide layout/table polish is local: the page now uses a wider operational canvas with create form and transaction ledger side by side on desktop, and the transaction table groups related fields for easier scanning. Browser review and deploy remain pending.
- `/sales/slaughter` table/detail behavior is local: newest created transactions sort first, completed/paid rows are closed with no update/cancel actions, open-row action buttons are smaller, rows open a read-only sale detail page, and `GET /api/sales-transactions/<sale_id>` returns one sale with items.
