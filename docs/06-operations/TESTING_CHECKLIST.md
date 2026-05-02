# Testing Checklist

## Purpose

Defines the checks required before accepting backend, n8n, Google Sheets, or app changes.

## General Rule

A change is not done until the affected docs are updated and the relevant checks pass.

## Order Lifecycle Tests

### Reject Order

Status: Phase 1.1 live verification passed. Keep this checklist as a regression test for future changes.

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
2. Run `POST /api/orders/<order_id>/cancel`.
3. Confirm `ORDER_MASTER.Order_Status = Cancelled`.
4. Confirm `ORDER_MASTER.Approval_Status = Not_Required`.
5. Confirm `Payment_Status = Cancelled`.
6. Confirm linked lines are released/cancelled.
7. Confirm reserved pigs become available again.
8. Confirm `ORDER_STATUS_LOG` records customer cancellation.
9. Confirm Sam sends a polite cancellation confirmation only after backend success.
10. Test the n8n two-turn customer cancel flow: first customer cancel intent sets `pending_action = cancel_order` and asks for confirmation; second customer `yes` calls `cancel_order`.
11. Test a non-confirming second message clears `pending_action` and does not cancel the order.

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
5. Until approval auto-reservation is implemented, confirm approval does not silently claim pigs are reserved.
6. After Phase 1.6 hardens reserve/release, confirm approval attempts to reserve active order lines and returns `reserve_warning` if reservation fails.
7. Confirm rejection cancels/releases linked non-cancelled/non-collected lines and writes the status log.
8. After outbound notifications are implemented, confirm approval and rejection trigger customer messages through the dedicated outbound workflow, not through Sam's inbound `1.0` workflow.

### Send For Approval From Sam

Status: Phase 1.4 happy path live verification passed on 2026-04-30. Keep the failure cases as required regression checks before broader lifecycle work.

Happy path:

1. Create or find a Draft order with at least one active `ORDER_LINE`.
2. Confirm `Payment_Method`, `Customer_Name`, and `Collection_Location` are populated.
3. Customer sends `Yes, please send it for approval`.
4. Confirm `Code - Build Order State` has `send_for_approval_intent = true`.
5. Confirm `Code - Decide Order Route` has `order_route = SEND_FOR_APPROVAL`.
6. Confirm `Call 1.2 - Send For Approval` returns `backend_success = true`.
7. Confirm `ORDER_MASTER.Order_Status = Pending_Approval` and `Approval_Status = Pending`.
8. Confirm Chatwoot `custom_attributes.order_status = Pending_Approval` and `payment_method` is preserved.
9. Confirm Sam says the order was sent for approval, not approved.

Regression checks:

1. Missing `Payment_Method`: Sam must ask for Cash/EFT or explain what is missing; order status must remain unchanged.
2. Already `Pending_Approval`: Sam must not submit again and should say it is already pending approval.
3. Backend `400` guard failure: n8n must return a customer-safe reply, not go silent. Use a Draft order with `Collection_Location` cleared, then ask `send it for approval`; expected result is `backend_success = false`, `backend_error = "Collection location is required before sending for approval."`, `ORDER_MASTER.Order_Status` remains `Draft`, and Sam tells the customer what is missing.

### Payment Method Capture

Status: Phase 1.3 live verification passed on 2026-04-29. Keep this checklist as a regression test for future order-finalization changes.

Test steps:

1. On an existing Draft order, send `I'll pay cash`.
2. Confirm `Code - Build Order State` has `detected_payment_method = Cash` and `order_state.payment_method = Cash`.
3. Confirm `Code - Build Enrich Existing Draft Payload` sends `payment_method = Cash`.
4. Confirm backend writes `ORDER_MASTER.Payment_Method = Cash`.
5. Confirm `HTTP - Set Conversation Context After Update` writes Chatwoot `custom_attributes.payment_method = Cash`.
6. Repeat with `EFT` and confirm `Payment_Method = EFT` and Chatwoot `payment_method = EFT`.
7. Send a next-turn message such as `When can I collect?` and confirm `Code - Normalize Incoming Message.PaymentMethod` reads the stored value.
8. Trigger cancel pending and confirm `payment_method` survives the Chatwoot full-object write.
9. Move the order beyond `Draft` and attempt to PATCH `payment_method`; confirm backend returns `400` and the sheet value remains unchanged.
10. In a conversation with no active draft, send `EFT`; confirm no backend update occurs and Sam moves into order discovery instead of storing payment method.
11. Trigger escalation and human reply; confirm `Sales_HumanEscalations.WebPaymentMethod` and `1.1 Release Conversation to Auto` preserve the value.

Known follow-up:

- Backend guard failures must produce customer-safe replies in n8n. Sam must not go silent when a backend safety check returns `400`.

## Requested Item Sync Tests

### First-Turn Draft Creation With Lines

Test steps:

1. Send a complete first-turn order request with quantity, category or weight range, sex preference, timing, and collection location.
2. Confirm `CREATE_DRAFT` creates `ORDER_MASTER`.
3. Confirm `Set - Draft Order Payload` sends `action = create_order_with_lines` when `requested_items[]` is non-empty.
4. Confirm `1.2 - Order Steward` routes to the `Create Order With Lines` branch.
5. Confirm `Code - Format Create With Lines Result` returns `success = true`, `sync_success = true`, and the new `order_id`.
6. Confirm `ORDER_LINES` contains active line rows for the new `Order_ID`.
7. Confirm Sam's reply includes the created order ID and does not claim reservation.

Live verification reference:

- 2026-04-29: `ORD-2026-879091` created in `ORDER_MASTER`; three matching `ORDER_LINES` rows created with `request_item_key = primary_1`.

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

## Web App Breeding Board Tests

The `/matings` page is a read-only operational view for mating and movement planning.

Test steps:

1. Open `/matings` and confirm the page loads without errors.
2. Confirm it reads from `GET /api/pig-weights/matings`.
3. Confirm overdue pregnancy checks and overdue farrowing records appear under `Needs Action Now`.
4. Confirm records near farrowing appear under `Move Soon / Prepare`.
5. Confirm records near the pregnancy-check window appear under `Upcoming Pregnancy Checks`.
6. Confirm sow and boar tags, pig IDs, current pen values, mating date, expected check date, pregnancy result, expected farrowing date, status/outcome, and linked litter values display where available.
7. Confirm the sow filter under the summary filters the board to the selected sow and `All sows` restores the full list.
8. Confirm cards are compact by default and each card's details button expands/collapses only that mating.
9. Confirm the top detail button expands all visible cards, then collapses all visible cards when clicked again.
10. Confirm sow and boar links open the correct `/pig/<pig_id>` pages.
11. Confirm linked litter links open `/litter/<litter_id>`.
12. Confirm `/master/add-mating` still works unchanged.
13. Confirm opening `/matings` does not write to Google Sheets.

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
