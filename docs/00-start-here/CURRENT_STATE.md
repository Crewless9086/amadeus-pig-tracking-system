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
- Phase 9 is parked for now. Phase 10A operating-system map is drafted in `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`, and Phase 10.1 Supabase foundation plan is drafted in `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`.
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
- Phase 10.2I is implemented locally: `GET /api/sales-transactions` reads Supabase sales transaction headers only, supports optional stream filtering, and reports `writes_to_sheets = false` / `writes_to_supabase = false`.
- Local verification passed on 2026-05-21: focused sales transaction/database tests passed at 17 tests, local missing-config route smoke returned safe `503`, and full local unittest suite passed at 174 tests.
- No records, write form, dashboard Rand totals, or order automation were added.
- Next step is deploy backend and verify `GET /api/sales-transactions` against Supabase.
