# Testing Checklist

## Purpose

Defines the checks required before accepting backend, n8n, Google Sheets, or app changes.

## General Rule

A change is not done until the affected docs are updated and the relevant checks pass.

## Order Lifecycle Tests

### Reject Order

Test steps:

1. Create or find an order with reserved lines.
2. Reject the order.
3. Confirm `ORDER_MASTER.Order_Status = Cancelled` or approved rejection status.
4. Confirm `ORDER_MASTER.Approval_Status = Rejected`.
5. Confirm linked non-cancelled/non-collected `ORDER_LINES` are `Line_Status = Cancelled` and `Reserved_Status = Not_Reserved`.
6. Confirm `ORDER_MASTER.Reserved_Pig_Count` is correct.
7. Confirm pigs become available again through formula views where appropriate.
8. Confirm `ORDER_STATUS_LOG` has a rejection entry.
9. Confirm Sam/web app does not say the order is approved or reserved.

### Customer Cancel

Test steps:

1. Create or find a draft/reserved customer order.
2. Run customer cancellation action.
3. Confirm `ORDER_MASTER.Order_Status = Cancelled`.
4. Confirm `ORDER_MASTER.Approval_Status = Not_Required`.
5. Confirm `Payment_Status = Cancelled` or `Not_Paid`.
6. Confirm linked lines are released/cancelled.
7. Confirm reserved pigs become available again.
8. Confirm `ORDER_STATUS_LOG` records customer cancellation.
9. Confirm Sam sends a polite cancellation confirmation only after backend success.

### Release Order

Test steps:

1. Reserve an order.
2. Release the order.
3. Confirm all linked reserved lines are no longer reserved.
4. Confirm cancelled/collected lines are not incorrectly changed.
5. Confirm repeated release does not break data.
6. Confirm reserved count is correct.

### Approve / Complete Guards

Test steps:

1. Try approving a cancelled order.
2. Try rejecting a completed order.
3. Try completing an invalid/unreserved order.
4. Confirm backend blocks unsafe transitions or returns clear errors.

## Requested Item Sync Tests

### Split Male/Female Request

Payload shape:

- `primary_1` = male request
- `primary_2` = female request

Expected:

- both keys create/preserve rows
- quantities match request
- no duplicate active rows after repeated sync
- no missing female/secondary rows

### Repeated Sync

Test steps:

1. Sync requested items once.
2. Sync the same requested items again.
3. Confirm no duplicate active lines.
4. Confirm existing reserved own pigs are handled correctly.

### Changed Request

Test steps:

1. Create order lines from an initial request.
2. Change requested quantity/category/sex split.
3. Sync again.
4. Confirm stale lines are released/cancelled.
5. Confirm new lines match the updated request.

### Partial Match

Test steps:

1. Request more pigs than available.
2. Confirm backend returns partial/no-match clearly.
3. Confirm Sam does not claim the order is fully updated.
4. Confirm incomplete lines do not silently look successful.

## n8n Order Steward Tests

For `1.2 - Amadeus Order Steward`, test only currently live `1.0` actions first:

- `create_order`
- `update_order`
- `sync_order_lines_from_request`

Each test must confirm:

- payload received correctly
- backend endpoint called correctly
- backend error returned clearly
- Sam gets only backend-confirmed truth

## Web App Order Tests

After backend behavior is safe, test the app for usability:

- order list shows useful status at a glance
- order detail shows lines and reservation state clearly
- reserve/release actions show clear progress/result messages
- reject/cancel buttons are understandable and safe
- logs/history are visible enough for debugging
- failed actions show helpful errors
- app reduces manual work instead of increasing it

## Google Sheets Checks

After any order change, inspect affected sheets/views:

- `ORDER_MASTER`
- `ORDER_LINES`
- `ORDER_STATUS_LOG`
- `PIG_OVERVIEW`
- `SALES_AVAILABILITY`
- `ORDER_OVERVIEW`

Formula sheets must not be manually edited to hide backend bugs.

## Documentation Checks

Before closing a change, update any affected files under:

- `docs/02-backend/`
- `docs/03-google-sheets/`
- `docs/04-n8n/`
- `docs/06-operations/`
- `docs/00-start-here/`
