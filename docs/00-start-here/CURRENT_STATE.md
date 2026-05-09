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
| Live order system | Stabilizing | Reject, customer cancel, first-turn create-with-lines, payment method capture, send-for-approval, Phase 1.5 lifecycle guards, and **Phase 1.6** (reserve/release batch hardening + order-detail success copy) are **complete and live-verified** (backend/sheets 2026-05-05; UI banner 2026-05-06). |
| Web app | Needs usability work | Reserve/release success messages on order detail now show API text, `changed_count`, and warnings (Phase 1.6). Remaining gap: **Phase 6** parity (e.g. approve/reject when `Pending_Approval`). |
| Media workflow | Disabled | `1.3` is official but must remain disabled until fixed and tested. |

## Completed Documentation Work

The following documentation areas are now usable as planning inputs:

- `docs/03-google-sheets/`: Google Sheets schema, ownership, formulas, fields, and per-sheet docs.
- `docs/04-n8n/`: n8n suite map, workflow rules, data flow, node responsibilities, protected logic, and four workflow exports.
- `docs/02-backend/`: backend API structure, order logic, data models, module structure, and refactor plan.

## Current Build Priority

The next build work should focus on **orders first**.

Reason:

- orders are live
- orders are the profit section
- incorrect order behavior can reserve the wrong pigs or block available stock
- Sam and the web app both depend on reliable backend order truth

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

- Phase 1.5 lifecycle guards — **Complete And Live-Verified** (see `NEXT_STEPS.md` §1.5): approval only from `Pending_Approval`, payment lock beyond `Draft`, reject/cancel blocked for `Completed`; auto-reservation and outbound notifications stay in Phase 1.8 / 1.9
- auto-reservation must wait until reserve/release behavior is hardened (Phase 1.6); until then, reservation remains a separate manual web-app or workflow action
- approval should eventually auto-reserve active order lines, because approval means the farm accepts and commits to the order
- once implemented, approval should not roll back if reservation fails; backend should log a warning and return `reserve_warning` for the admin web app
- approval/rejection customer notifications should use a separate outbound n8n workflow triggered by backend webhook, not Sam's inbound `1.0` workflow
- outbound notification planning depends on storing a reliable Chatwoot lookup key, preferably `ConversationId` on `ORDER_MASTER`

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
- viewing matings in a clear breeding board for pregnancy checks, farrowing preparation, and movement planning
- understanding reservation status
- approving/rejecting/cancelling orders safely, with order detail actions visible when `Pending_Approval` (parity with workflows and backend rules)
- releasing pigs correctly
- showing logs/history
- producing practical farm printouts, starting with a pre-weighing weekly weight sheet that has blank capture columns and can be printed from a phone or laptop
- reducing manual debugging work

Do not focus on app polish before order behavior is correct.

## Next Decision Point

Pick the next item from `docs/00-start-here/NEXT_STEPS.md`. **Phase 1.7 is closed** (slim reply payload live-verified). **Primary next implementation focus: Phase 1.8** (approval auto-reservation). **Phase 6** (order-detail parity) remains parallel polish when useful — see `NEXT_STEPS` choice point.
