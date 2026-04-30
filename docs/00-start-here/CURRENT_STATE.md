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
| Live order system | Stabilizing | Reject, customer cancel, first-turn create-with-lines, and payment method capture are live-verified. Send-for-approval, reserve/release robustness, and lifecycle guards remain priority. |
| Web app | Needs usability work | App should support operations, not create extra manual work. Focus after order structure is stable. |
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
- missing payment method and already-pending regression checks passed
- backend `400` customer-safe reply regression still needs re-test after importing the latest `1.2`; expected behavior is `backend_success = false`, `backend_error` contains the missing field, and Sam tells the customer what is missing

Approve/reject lifecycle direction:

- approval should eventually auto-reserve active order lines, because approval means the farm accepts and commits to the order
- auto-reservation must wait until reserve/release behavior is hardened; until then, reservation remains a separate manual web-app action
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

### Sales Agent Reply Payload Needs Slimming

Current risk:

- `Ai Agent - Sales Agent` receives a large merged payload containing raw Chatwoot webhook data, debug fields, sync internals, and final order context
- this did not block Fix C, but it increases prompt noise and makes reply behavior harder to reason about

Preferred follow-up:

- add a `Code - Build Sales Reply Context` node before Sam
- pass only the fields needed for the reply: customer message, short conversation summary, order action, order ID/status, backend success, sync success, slim order state, and explicit reply instruction
- keep raw/debug data available in previous nodes for diagnostics, not in Sam's prompt

## Web App Current Concern

The app must become useful for daily operations. It should help with:

- viewing orders clearly
- understanding reservation status
- approving/rejecting/cancelling orders safely
- releasing pigs correctly
- showing logs/history
- reducing manual debugging work

Do not focus on app polish before order behavior is correct.

## Next Decision Point

Pick the next item from `docs/00-start-here/NEXT_STEPS.md`. The immediate check is Phase 1.4 Test C after importing the updated `1.2` workflow. After that, continue with Phase 1.5 lifecycle guards, Phase 1.6 reserve/release hardening, and the planned outbound approval/rejection notification flow.
