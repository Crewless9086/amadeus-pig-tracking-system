# Backend Refactor Plan

## Purpose

Plans backend cleanup and hardening after documentation alignment.

## Current Rule

No backend refactor should happen casually. Each change should have a focused goal, small file scope, and verification checklist.

## Phase 1: Stabilize Order Lifecycle

Goal: make reject, cancel, release, and status logging safe.

Tasks:

- Reject behavior is implemented and live-verified; keep regression checks in the testing checklist.
- Customer cancel endpoint/action is implemented and live-verified; keep regression checks in the testing checklist.
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

- `order_read.py` - extracted; active customer lookup tests target the new module directly while routes keep the `order_service` public names
- `order_write.py` - extracted; create/update/order-line CRUD tests target the new module directly while routes keep the `order_service` public names
- `order_matching.py`
- `order_line_sync.py` - extracted; requested-item sync tests target the new module directly while routes keep the `order_service` public name
- `order_reservation.py` - extracted; `order_service.reserve_order_lines` and `order_service.release_order_lines` remain available through imported compatibility names
- `order_lifecycle.py` - extracted; lifecycle tests target the new module directly while routes keep the `order_service` public names
- `order_status_log.py` - extracted; status-log callers now use the focused module through the service facade where needed
- `integrations/n8n_orders.py`

## Phase 5: Add Verification Coverage

Goal: prevent regressions.

Phase 7.0A inventory:

- `docs/02-backend/ORDER_VERIFICATION_MATRIX.md`

Phase 7.0B harness:

- use stdlib `unittest`
- mock Google Sheets boundaries
- run with `.\venv\Scripts\python.exe -m unittest discover -s tests -v`
- passing tests cover `create_order`, `update_order`, basic order-line CRUD, `reserve_order_lines`, `release_order_lines`, `send_order_for_approval`, `approve_order` reserve-warning behavior, `reject_order`, `cancel_order`, `complete_order`, `sync_order_lines_from_request`, `get_active_customer_order_context`, direct `order_status_log.py` writes, and mocked route smoke behavior for order detail, create/update order, create/update/delete order lines, reserve/release, lifecycle actions, and sync validation/auto-quote attachment

Phase 7.0C first extraction:

- `modules/orders/order_status_log.py` owns status log ID generation and appending rows to `ORDER_STATUS_LOG`.
- `modules/orders/order_service.py` keeps `_write_order_status_log(...)` as a stable wrapper so existing service code, route behavior, and tests are not forced to change in the same step.
- Verified with the full local mocked suite.

Phase 7.0C second extraction:

- `modules/orders/order_reservation.py` owns `reserve_order_lines(...)` and `release_order_lines(...)`.
- `modules/orders/order_service.py` imports those names so routes and lifecycle code keep the same public call surface.
- Reservation tests now target `order_reservation.py` directly; lifecycle tests still patch `order_service.reserve_order_lines` to protect the approve-order integration point.
- Verified with the full local mocked suite.

Phase 7.0C third extraction:

- `modules/orders/order_write.py` owns `create_order(...)`, `update_order(...)`, `create_order_line(...)`, `update_order_line(...)`, and `delete_order_line(...)`.
- `modules/orders/order_service.py` imports those names so existing routes and create-with-lines integration continue to call the same public names.
- CRUD service tests now target `order_write.py` directly.
- Verified with the full local mocked suite.

Phase 7.0C fourth extraction:

- `modules/orders/order_read.py` owns `list_orders(...)`, `get_order_detail(...)`, and `get_active_customer_order_context(...)`.
- `modules/orders/order_service.py` imports those names so existing routes keep the same public call surface.
- Active customer lookup tests now target `order_read.py` directly; route tests still protect the `order_service` import path.
- Verified with the full local mocked suite.

Phase 7.0C fifth extraction:

- `modules/orders/order_line_sync.py` owns requested-item matching and `sync_order_lines_from_request(...)`.
- `modules/orders/order_service.py` imports that name so existing routes and create-with-lines integration keep the same public call surface.
- Sync tests now target `order_line_sync.py` directly.
- The zero-match auto-cancel branch uses a runtime import of `order_service.cancel_order(...)` to avoid circular imports while lifecycle remains in `order_service.py`.
- Verified with the full local mocked suite.

Phase 7.0C sixth extraction:

- `modules/orders/order_lifecycle.py` owns `send_order_for_approval(...)`, `approve_order(...)`, `reject_order(...)`, `cancel_order(...)`, and `complete_order(...)`.
- `modules/orders/order_service.py` imports those names so existing routes keep the same public call surface.
- Lifecycle tests now target `order_lifecycle.py` directly; route tests still protect the `order_service` import path.
- Verified with the full local mocked suite.

Phase 7.0C cleanup:

- Legacy renamed bodies were removed from `order_service.py`.
- Unused imports/constants were removed from `order_service.py`.
- `order_service.py` is now a compatibility facade for routes, document services, report services, and workflow-facing code.
- Keep `create_order_with_lines(...)` in `order_service.py` until a deliberate orchestration module is chosen, because it coordinates create, sync, and cancel behavior across extracted modules.
- Verified with the full local mocked suite after route CRUD smoke coverage: 63 tests passing on 2026-05-18.

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

Detailed Phase 7.2 planning source:

- `docs/02-backend/DATABASE_SCALING_PLAN.md`

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
- customer cancel endpoint/action is implemented and live-verified.
- reserve/release cancelled/collected-line semantics are hardened; keep regression checks before touching order lifecycle code.
- partial matches must not silently create incomplete orders.
