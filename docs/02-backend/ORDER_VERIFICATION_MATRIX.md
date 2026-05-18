# Order Verification Matrix

## Purpose

Phase 7.0 starts by protecting current order behavior before any backend refactor.

This matrix identifies the backend behaviors that must stay stable while `modules/orders/order_service.py` is cleaned up or split into smaller modules.

## Scope

In scope for Phase 7.0:

- order lifecycle transitions
- requested-item line sync
- reservation/release semantics
- active order lookup for Sam/web app
- sheet write boundaries and status logs

Out of scope for Phase 7.0:

- meat/carcass business-module implementation
- database migration
- broad n8n payload cleanup
- large `order_service.py` split before verification exists

## Current Backend Surface

Primary route file:

- `modules/orders/order_routes.py`

Primary service file:

- `modules/orders/order_service.py`

Supporting files:

- `modules/orders/order_validation.py`
- `modules/orders/order_intake_service.py`
- `modules/documents/quote_service.py`
- `modules/documents/invoice_service.py`
- `modules/documents/document_service.py`

Primary sheets touched by order service:

- `ORDER_MASTER`
- `ORDER_LINES`
- `ORDER_STATUS_LOG`
- `ORDER_OVERVIEW`
- `SALES_AVAILABILITY`
- `SALES_PRICING`
- `PIG_MASTER` through `complete_order`

## Verification Rule

Before moving behavior into new modules, the behavior must be covered by at least one of:

- local mocked-service test
- Flask test-client route check with mocked service/sheet boundary
- documented manual/live checklist item

Live Google Sheets tests should be narrow because previous regression batches hit Google Sheets API quota.

## Protected Behavior Matrix

| Behavior | Route / entry point | Service functions | Sheets read | Sheets written | Required verification |
| --- | --- | --- | --- | --- | --- |
| List orders | `GET /api/orders` | `list_orders`, `_build_order_line_rollups` | `ORDER_OVERVIEW`, `ORDER_MASTER`, `ORDER_LINES` | none | Local route smoke: returns `success`, `count`, `orders[]`; cancelled/completed remain visible for filtered UI. |
| Order detail | `GET /api/orders/<order_id>` | `get_order_detail` | `ORDER_OVERVIEW`, `ORDER_MASTER`, `ORDER_LINES`, `ORDER_DOCUMENTS` through route | none | Local route smoke for known/mocked order; missing order returns 404. |
| Active customer lookup | `GET /api/orders/active-customer-context` | `get_active_customer_order_context`, `_active_customer_order_lookup_from_candidates`, `_safe_order_context_from_detail` | `ORDER_MASTER`, `ORDER_OVERVIEW`, `ORDER_LINES` | none | Unit checks for exact `order_id`, single conversation match, multiple matches, no match, terminal-order exclusion. |
| Create draft order | `POST /api/master/orders` | `create_order`, `_write_order_status_log` | none or ID helpers | `ORDER_MASTER`, `ORDER_STATUS_LOG` | Mocked append test: Draft/Pending defaults, payment/status fields, status log row. |
| Update order header | `PATCH /api/master/orders/<order_id>` | `update_order` | `ORDER_MASTER` | `ORDER_MASTER` | Mocked update test: Draft-only payment update allowed; non-Draft payment update blocked; no valid fields blocked. |
| Create order line | `POST /api/master/order-lines` | `create_order_line` | `ORDER_LINES` | `ORDER_LINES` | Mocked append test: duplicate active pig on same order blocked; default line statuses correct. |
| Update order line | `PATCH /api/master/order-lines/<line_id>` | `update_order_line` | `ORDER_LINES` | `ORDER_LINES` | Mocked update test: unit price/notes update, missing line blocked. |
| Delete order line | `DELETE /api/master/order-lines/<line_id>` | `delete_order_line` | `ORDER_LINES` | `ORDER_LINES` | Mocked update test: line becomes `Cancelled`, reservation cleared, terminal behavior preserved. |
| Requested-item sync | `POST /api/master/orders/<order_id>/sync-lines` | `sync_order_lines_from_request`, `_get_matching_available_pigs`, `_append_order_line_from_match`, `_cancel_order_lines` | `ORDER_MASTER`, `SALES_AVAILABILITY`, `ORDER_LINES`, `SALES_PRICING` | `ORDER_LINES`, sometimes `ORDER_MASTER` for no-match auto-cancel | Unit/mocked tests for exact match, split male/female keys, repeated sync no duplicates, stale line cancellation, partial match, no-match auto-cancel where enabled. |
| Create with lines | `POST /api/master/orders/create-with-lines` | `create_order_with_lines`, `create_order`, `sync_order_lines_from_request` | same as create + sync | `ORDER_MASTER`, `ORDER_LINES`, `ORDER_STATUS_LOG` | Mocked route/service test: order created only reports useful success when sync behavior is known; metadata returned for intake and quote readiness. |
| Reserve order lines | `POST /api/orders/<order_id>/reserve` | `reserve_order_lines` | `ORDER_MASTER`, `ORDER_LINES` | `ORDER_LINES`, `ORDER_MASTER` | Unit/mocked tests: eligible lines reserve; cancelled/collected/no-pig skipped; already reserved idempotent; no eligible lines returns failure/422 through route; `changed_count` correct. |
| Release order lines | `POST /api/orders/<order_id>/release` | `release_order_lines` | `ORDER_MASTER`, `ORDER_LINES` | `ORDER_LINES`, `ORDER_MASTER` | Unit/mocked tests: reserved lines release; cancelled/collected not incorrectly changed; second release idempotent; `Reserved_Pig_Count` recalculated. |
| Send for approval | `POST /api/orders/<order_id>/send-for-approval` | `send_order_for_approval`, `_write_order_status_log`, `_notify_n8n_order_approval_request` | `ORDER_MASTER`, `ORDER_LINES` | `ORDER_MASTER`, `ORDER_STATUS_LOG` | Tests for Draft-only guard, payment required, customer required, collection required, active line required, status log written. |
| Approve order | `POST /api/orders/<order_id>/approve` | `approve_order`, `reserve_order_lines`, `_write_order_status_log`, `_notify_order_customer_notification` | `ORDER_MASTER`, `ORDER_LINES` | `ORDER_MASTER`, `ORDER_STATUS_LOG`, `ORDER_LINES` through reserve | Tests for Pending_Approval-only guard, approval not rolled back on reserve warning, `reserve_warning` returned, status log warning attempted. |
| Reject order | `POST /api/orders/<order_id>/reject` | `reject_order`, `_cancel_order_lines`, `_write_order_status_log`, `_notify_order_customer_notification` | `ORDER_MASTER`, `ORDER_LINES` | `ORDER_MASTER`, `ORDER_LINES`, `ORDER_STATUS_LOG` | Tests for completed-order guard, linked active lines cancelled/released, `Approval_Status = Rejected`, `Reserved_Pig_Count = 0`, log written. |
| Customer cancel | `POST /api/orders/<order_id>/cancel` | `cancel_order`, `_cancel_order_lines`, `_write_order_status_log` | `ORDER_MASTER`, `ORDER_LINES` | `ORDER_MASTER`, `ORDER_LINES`, `ORDER_STATUS_LOG` | Tests for completed-order guard, already rejected/cancelled guard, active lines cancelled/released, `Approval_Status = Not_Required`, `Payment_Status = Cancelled`, reason logged. |
| Complete order | `POST /api/orders/<order_id>/complete` | `complete_order`, `_write_order_status_log` | `ORDER_MASTER`, `ORDER_LINES` | `ORDER_LINES`, `PIG_MASTER`, `ORDER_MASTER`, `ORDER_STATUS_LOG` | Tests for Approved-only guard, no active lines blocked, no-pig lines blocked, lines become `Collected`, pigs become `Sold`, order becomes `Completed`. |
| Quote generation readiness hooks | route-level after create/update/sync plus `POST /api/orders/<order_id>/quote/send-latest` | `auto_generate_quote_if_ready`, `auto_generate_quote_if_ready_with_retry` | `ORDER_MASTER`, `ORDER_LINES`, `ORDER_DOCUMENTS`, settings through document services | `ORDER_DOCUMENTS`, Drive through document services | Keep current live-verified behavior; avoid touching in Phase 7.0 unless tests expose a direct order-service contract break. |

## Suggested First Automated Coverage

Start with mocked tests around these behaviors because they are high-risk and do not need live Sheets:

1. `reserve_order_lines`
2. `release_order_lines`
3. `send_order_for_approval`
4. `approve_order` with reserve warning
5. `reject_order`
6. `cancel_order`
7. `complete_order`
8. `sync_order_lines_from_request` exact/split/repeat/no-match cases

## Local Test Harness

Harness selected for Phase 7.0B:

- Python standard library `unittest`.
- `unittest.mock` for Google Sheets/service boundaries.
- No live Google Sheets reads or writes.

Run command:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Current first coverage:

- `tests/test_order_service_reservation.py`
- `reserve_order_lines`
- `release_order_lines`
- `tests/test_order_service_lifecycle.py`
- `send_order_for_approval`
- `approve_order` reserve-warning path
- `reject_order`
- `cancel_order`
- `complete_order`
- `sync_order_lines_from_request`
- `get_active_customer_order_context`
- `create_order`, `update_order`, `create_order_line`, `update_order_line`, `delete_order_line`
- `modules/orders/order_status_log.py`
- `modules/orders/order_reservation.py`
- `modules/orders/order_write.py`
- `modules/orders/order_read.py`
- `modules/orders/order_line_sync.py`
- `modules/orders/order_lifecycle.py`
- `tests/test_order_routes.py`

Current passing checks:

- reserve eligible active line and report skipped no-pig / terminal lines
- reserve already-reserved line idempotently without a sheet row write
- reserve failure when no eligible lines exist
- release reserved lines and clear cancelled reserved lines without changing cancelled status
- release idempotently when no reservations exist
- missing order guard
- send-for-approval Draft/payment/customer/location/active-line guards
- send-for-approval status update and status log
- approve Pending_Approval guard
- approve keeps approval when auto-reserve returns warning/failure and records manual follow-up warning
- reject completed-order guard
- reject cancels only active linked lines, marks `Cancelled | Rejected`, resets reserved count, and logs the transition
- cancel completed-order guard
- cancel already-rejected guard
- cancel cancels only active linked lines, marks `Cancelled | Not_Required`, sets payment cancelled, resets reserved count, and logs the customer reason
- complete Approved-only guard
- complete no-active-lines guard
- complete no-pig active-line guard
- complete marks active order lines as `Collected`, marks linked pigs as `Sold`, updates the order to `Completed`, and writes a status log
- sync exact match creates lines and reports complete fulfillment
- sync split male/female request keys do not reuse the same pig
- sync still allocates a later split item when an earlier split item has no match
- sync replaces existing active lines for the same request key by cancelling stale lines before appending replacements
- sync partial match reports incomplete items and unmatched quantity
- sync zero-match auto-cancel path calls the customer cancel flow when explicitly requested
- active customer lookup requires at least one identifier
- active customer lookup exact `order_id` returns safe context for active orders, `terminal_order` for completed/cancelled orders, and `no_match` for missing orders
- active customer lookup conversation match excludes terminal orders, loads detail for one active match, and returns safe summaries for multiple active matches
- active customer lookup phone matching normalizes digits and excludes terminal orders
- create order appends Draft/Pending defaults and writes status log; status-log failure returns warning without failing order creation
- update order writes allowed fields, blocks missing/terminal orders, blocks empty updates, and locks payment changes beyond Draft
- create order line appends available pigs with Draft/Not_Reserved defaults and blocks unavailable, already-reserved, and duplicate active pigs
- update order line edits active lines and blocks terminal lines
- delete order line marks active lines `Cancelled | Not_Reserved` and blocks reserved or terminal lines
- status log module appends the expected `ORDER_STATUS_LOG` row shape directly
- reservation module directly covers reserve/release eligibility, idempotency, terminal-line handling, and header reserved-count updates
- write module directly covers create/update order and basic order-line CRUD behavior
- read module directly covers active customer lookup and owns list/detail read behavior for routes
- line-sync module directly covers exact match, split request keys, partial/no-match reporting, stale-line replacement, and zero-match auto-cancel integration
- lifecycle module directly covers approval submission, approval, rejection, customer cancel, and completion behavior
- route smoke checks for order detail 200/404, create/update order, create/update/delete order lines, reserve 200/422, release guard 400, lifecycle guard 400s, cancel reason forwarding, sync validation 400, and sync success auto-quote attachment

Phase 7.0 completion:

- Complete on 2026-05-18 after the controlled production create-with-lines checkpoint passed.
- Next backend work should start from the next active phase in `docs/00-start-here/NEXT_STEPS.md`.

Cleanup status:

- `order_service.py` legacy renamed bodies and unused imports were removed on 2026-05-18.
- The file is now a compatibility facade over the extracted order modules, with `create_order_with_lines(...)` kept as the current orchestration wrapper.
- Full mocked verification passed after cleanup, route CRUD smoke coverage, and Google Sheets cache coverage: 65 tests green.
- Local-code/live-data checkpoint passed on 2026-05-18: `ORD-2026-900422` created through create-with-lines, synced one active line, auto-generated quote `Q-2026-900422`, then cancelled cleanly.
- Production checkpoint on 2026-05-18 did not pass cleanly before redeploy: `ORD-2026-D15B1E` was written with one active line but production returned `500` and no quote document. Cleanup cancelled the order and active lookup returned `no_match`.
- Post-deploy production retest on 2026-05-18 still returned `500`: `ORD-2026-CF8C38` was written with one active line and generated quote `Q-2026-CF8C38`, then cleanup cancelled the order and active lookup returned `no_match`.
- Render logs confirmed the `500` source was Google Sheets `429` read quota at spreadsheet metadata fetch. A cache/retry fix is prepared in `services/google_sheets_service.py` to reuse the gspread client, spreadsheet, and worksheet handles and retry quota-related `APIError` calls.
- Final production checkpoint passed after deploying the Google Sheets cache/retry fix: `ORD-2026-BBF8B3` returned cleanly with `success = true`, `create_success = true`, `sync_success = true`, `complete_fulfillment = true`, one active line, and generated quote `Q-2026-BBF8B3`. Cleanup cancelled the order and active lookup returned `no_match`.

## Service Boundary Candidates

Do not split yet. Once verification exists, likely module boundaries are:

| Candidate module | Behavior owned |
| --- | --- |
| `order_read.py` | list/detail/active customer lookup/read-only rollups |
| `order_write.py` | create/update order header and basic line CRUD |
| `order_line_sync.py` | requested-item sync and matching lifecycle |
| `order_matching.py` | sales availability matching and alternatives |
| `order_reservation.py` | reserve/release semantics |
| `order_lifecycle.py` | send-for-approval/approve/reject/cancel/complete |
| `order_status_log.py` | status log row creation |
| `order_notifications.py` | n8n/customer notification wrappers |
| `order_sheet_gateway.py` | eventual Google Sheets boundary wrapper |

## Open Decisions

- Whether to add tests directly against `order_service.py` with monkeypatched sheet functions first, or introduce a thin sheet gateway before test expansion.
- Whether to use `pytest` or keep initial tests as simple Python unittest files.
- Whether to include route-level tests in the first pass or start at service-function level.
- Which live regression smoke is safe after local mocked coverage, given Google Sheets quota pressure.

## Phase 7.0A Completion Criteria

- This matrix exists and is linked from `NEXT_STEPS.md`.
- Phase 7.0B can start by choosing a test harness approach.
- No service refactor has started yet.
