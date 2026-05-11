# Backend Refactor Plan

## Purpose

Plans backend cleanup and hardening after documentation alignment.

## Current Rule

No backend refactor should happen casually. Each change should have a focused goal, small file scope, and verification checklist.

## Phase 1: Stabilize Order Lifecycle

Goal: make reject, cancel, release, and status logging safe.

Tasks:

- Reject behavior is implemented and live-verified; keep regression checks in the testing checklist.
- Customer cancel endpoint/action is implemented; verify against live Google Sheets.
- Ensure cancel/reject appends `ORDER_STATUS_LOG`.
- Ensure cancelled/rejected orders cannot keep pigs reserved.
- Customer cancellation uses `Approval_Status = Not_Required` and `Payment_Status = Cancelled`; keep regression checks in the testing checklist.
- Add guards so terminal/completed orders cannot be approved/rejected incorrectly.

## Phase 2: Fix Requested Item Sync

Goal: make `sync_order_lines_from_request` reliable for split requests.

Tasks:

- Preserve `primary_1`, `primary_2`, and future split keys consistently.
- Prevent repeated syncs from creating duplicates.
- Cancel/release stale lines before replacing them.
- Decide intended partial/no-match behavior.
- Ensure `ORDER_LINES` totals match requested quantity before returning success to Sam.
- Phase 4.3 resolved `intent_type` / `status`: `intent_type` is optional validated metadata; `status` defaults to `active` and non-active values are rejected.

## Phase 3: Improve Order Review For Sam

Goal: let Sam understand saved order state safely.

Preferred direction:

- Add an Order Steward/backend review action rather than direct AI access to `ORDER_OVERVIEW`.
- Backend should find relevant customer orders, filter fields, and return a safe summary.
- Sam can then answer based on backend-confirmed truth.

Possible action name:

- `review_order`
- `find_customer_orders`
- `get_active_customer_order_context`

## Phase 4: Split `order_service.py`

Goal: reduce one large service file into focused modules.

Proposed modules:

- `order_read.py`
- `order_write.py`
- `order_matching.py`
- `order_line_sync.py`
- `order_reservation.py`
- `order_lifecycle.py`
- `order_status_log.py`
- `integrations/n8n_orders.py`

## Phase 5: Add Verification Coverage

Goal: prevent regressions.

Minimum checks:

- create draft order
- update draft order
- sync split requested items male/female
- repeat sync without duplicates
- partial match response
- reserve order
- release order
- reject releases reserved lines
- customer cancel releases reserved lines
- complete order updates lines and pigs
- Sam/Order Steward only reports success after backend confirms

## Known Bugs / Risks To Track

- `sync_order_lines_from_request` has had split-item issues where `primary_2` rows were missing or not updated correctly.
- reject reserved-line cleanup is implemented and live-verified.
- customer cancel endpoint/action is implemented but needs live Google Sheets verification.
- reserve may need stronger guards against cancelled/collected lines.
- partial matches must not silently create incomplete orders.
