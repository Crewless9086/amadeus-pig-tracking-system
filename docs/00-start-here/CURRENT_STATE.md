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
| Live order system | Needs stabilization | This is the current profit-critical area. Fix before expanding features. |
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

Current backend behavior:

- `reject_order()` blocks completed orders from being rejected
- it cancels linked non-cancelled/non-collected order lines
- it sets linked line reservations back to `Not_Reserved`
- it resets `ORDER_MASTER.Reserved_Pig_Count` to `0`
- it sets `Order_Status = Cancelled` and `Approval_Status = Rejected`
- it writes `ORDER_STATUS_LOG` when the rejection or cleanup changes state

Remaining watch point:

- verify formula views recover availability correctly after real Google Sheets execution

### Customer Cancellation Is Not Implemented

Current state:

- no dedicated customer cancel endpoint/action exists

Approved target:

- `Order_Status = Cancelled`
- `Approval_Status = Not_Required`
- `Payment_Status = Cancelled` or `Not_Paid`
- linked lines released/cancelled
- `ORDER_STATUS_LOG` records customer cancellation

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

Move from documentation into implementation planning for **Phase 1: Order Lifecycle Stabilization**.
