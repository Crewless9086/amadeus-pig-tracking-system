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
- Phase 9.3 is deployed and owner-verified: the weight form shows the selected pig's current pen beside `Moved To Pen (Optional)` without changing the save payload.
- Phase 9.4 current slice is deployed and owner-verified: read-only weight report endpoint and `/weight-report` page include visual usability refinements, duplicate prevention is live, and numeric pig tags display correctly as three digits. Full edit/delete/void audit, interactive report rows, sortable report headers, and feed-guidance planning remain parked for later phases.
- Phase 9.5 is deployed/browser-visible: the dashboard monthly sales count now shows total sales exits plus livestock, slaughter/abattoir, and future meat streams from `PIG_MASTER` exits. Follow-up 9.5B is planned for clearer sales stream counts and Rand values once each stream's value source is defined.
- Phase 9.6A is deployed and browser-verified: `/print-sheets` provides a read-only weekly weight capture sheet with English labels, all-active default, multi-pen filtering, browser print support, and no Google Sheets writes.
- Phase 9 is parked for now. Phase 10A operating-system map is drafted in `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`, and Phase 10.1 Supabase foundation plan is drafted in `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`.
- Phase 10.1 owner comments have been captured as guided defaults: use the existing Supabase Pro project as the foundation/staging workspace first, use plain SQL migrations in `supabase/migrations/`, keep Supabase behind the Flask backend, add `/health/database`, migrate orders/sales first, review telemetry after the first database path is proven, and keep Google Sheets visible until the database-backed path is trusted.
- Phase 10.1 first implementation slice is local: `supabase/migrations/` exists as the migration home, backend route `GET /health/database` exists, and the route is designed to be safe when `DATABASE_URL` is missing.
- Local verification passed on 2026-05-21: focused database tests passed, full local unittest suite passed at 132 tests, and `/health/database` returns safe `503` / `not_configured` before `DATABASE_URL` is added.
- Next step is owner adding Supabase connection env vars directly in Render for deployed `/health/database` verification.
