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

Current state:

- By-ID review is already live through `GET /api/orders/<order_id>` and `1.2` `get_order_context`.
- The missing backend/steward capability is safe active customer order lookup when Sam does not already have the exact `order_id`.

Preferred direction:

- Add an Order Steward/backend lookup action rather than direct AI access to `ORDER_OVERVIEW` or the full `/api/orders` list.
- Backend should find relevant customer orders by safe identifiers (`conversation_id`, `customer_phone`, exact `order_id`), filter fields, and return a safe summary.
- Sam can then answer based on backend-confirmed truth.
- Keep `ORDER_MASTER` as the operational source for now; archive/history splitting is a future scaling decision, not part of the immediate review fix.

Possible action names:

- `get_active_customer_order_context` - preferred for the next implementation.
- `find_customer_orders` - useful companion for multiple matches/history.
- `review_order` - optional wrapper name if the behavior becomes broader later.

Archive/history note:

- Do not create a separate `ORDER_HISTORY` sheet yet.
- Use `ORDER_STATUS_LOG`, `ORDER_DOCUMENTS`, `ORDER_LINES`, and filtered API views for history.
- Revisit an archive/read-model only when sheet size, formula performance, or operations clutter justifies the extra source-of-truth complexity.

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

## Phase 6: Database Scaling Review

Goal: plan the eventual move away from Google Sheets as the transactional database before order volume grows materially.

Current position:

- Keep Google Sheets for now because it gives strong operator visibility and the current priority is stabilizing behavior.
- Recent Google Sheets `429` quota errors came from automated multi-case live tests, but they are a valid signal that Sheets is not the right long-term transaction store.
- This is planning only; do not start migration until order/intake/document behavior is stable.

Preferred future direction:

- Evaluate Supabase Postgres first.
- Keep Google Sheets as reporting/export/operator views if useful.
- Use Postgres as source of truth for order, intake, line, document, and eventually stock transactions.
- Add a backend repository/data-access layer before migration so services do not depend directly on `services/google_sheets_service.py`.

Initial migration candidates:

- `ORDER_MASTER`
- `ORDER_LINES`
- `ORDER_INTAKE_STATE`
- `ORDER_INTAKE_ITEMS`
- `ORDER_DOCUMENTS`

Cost assumption:

- Plan around USD 25/month as a practical starting point for Supabase Postgres-style production use.
- Re-check pricing and requirements before implementation.

## Known Bugs / Risks To Track

- `sync_order_lines_from_request` has had split-item issues where `primary_2` rows were missing or not updated correctly.
- reject reserved-line cleanup is implemented and live-verified.
- customer cancel endpoint/action is implemented but needs live Google Sheets verification.
- reserve may need stronger guards against cancelled/collected lines.
- partial matches must not silently create incomplete orders.
