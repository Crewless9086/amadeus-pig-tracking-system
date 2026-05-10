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

### Approval Auto-Reservation

Applies to `NEXT_STEPS.md` Phase 1.8.

Status:

- Complete and live-verified on 2026-05-09.
- Mixed-line verification: `ORD-2026-102250` reserved one active line, skipped one cancelled line, did not roll back approval, and wrote a status log warning.
- Clean all-eligible verification: `ORD-2026-7C79A8` reserved two active lines with no warning.
- All-ineligible verification: `ORD-2026-0FB697` approved with no reserved lines, returned `reserve_warning`, and wrote a status log warning.

Pre-check:

1. Confirm live headers match the documented order sheets: `ORDER_MASTER`, `ORDER_LINES`, and `ORDER_STATUS_LOG`.
2. Confirm `ORDER_MASTER.Payment_Method` exists and remains available for send-for-approval/approval checks.

Test steps:

1. Approve a `Pending_Approval` order with all active lines eligible for reservation.
2. Confirm `ORDER_MASTER.Order_Status = Approved` and `Approval_Status = Approved`.
3. Confirm eligible `ORDER_LINES` are `Line_Status = Reserved` and `Reserved_Status = Reserved`.
4. Confirm `ORDER_MASTER.Reserved_Pig_Count` matches the actual reserved line count.
5. Approve an order with mixed eligible, cancelled, collected, or no-pig lines.
6. Confirm terminal/no-pig lines are skipped and reported, not modified incorrectly.
7. Force or simulate a reservation warning/failure where practical.
8. Confirm approval is not rolled back, `reserve_warning` is returned, and `ORDER_STATUS_LOG` records the manual follow-up.
9. Confirm the web app can show the returned warning clearly to the admin/operator.

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

## Phase 1.9 Outbound Notification Tests

Phase 1.9 live verification completed on 2026-05-09:

1. Live `ORDER_MASTER` has `ConversationId` after `Payment_Method`.
2. `1.4 - Outbound Order Notification` imported/configured in n8n after fixing blocked `$env` expressions and JSON body expression syntax.
3. Direct webhook smoke test to `conversation_id = 1742` returned `success = true`, `sent = true`, `event_type = order_approved`.
4. Approval backend test: `ORD-2026-36CDE4` moved to `Approved | Approved`, one line reserved, `Reserved_Pig_Count = 1`, and `customer_notification_sent = true`.
5. Rejection backend test: `ORD-2026-C3CEDF` moved to `Cancelled | Rejected`, one line cancelled/released, `Reserved_Pig_Count = 0`, and `customer_notification_sent = true`.
6. No notification warning was returned for either backend transition.

Regression checks for future edits:

- Confirm new orders created through `1.0`/`1.2` store `conversation_id` on `ORDER_MASTER.ConversationId`.
- Confirm approval and rejection still send the exact agreed message texts.
- Confirm failed notification delivery does not roll back the order transition and writes an `ORDER_STATUS_LOG` warning.

## Phase 2.3 Quote Generation Tests

Phase 2.3 first live quote generation test completed on 2026-05-10:

1. `POST /api/orders/<order_id>/quote` was added.
2. Missing-order smoke test returned `400` with `Order not found.`
3. Live quote generated for `ORD-2026-01E18A`.
4. Result document: `DOC-2026-49BF16`, `Q-2026-01E18A`, version `1`.
5. Generated file: `QUO_2026_05_10_01E18A_V1_(R3,200.00)_Cash.pdf`.
6. Drive file ID: `1FA50hJUf7q41jKGX3trRcEceaJbfSLk1`.
7. `ORDER_DOCUMENTS` row was appended and verified.
8. Drive metadata was verified as `application/pdf`.
9. Draft quote note was stored: `Draft quote - subject to availability and approval`.

Phase 2.3 close-out tests completed on 2026-05-10:

1. Project owner visually inspected the generated PDF and confirmed it looked good.
2. V2 quote generated for `ORD-2026-01E18A`: `DOC-2026-E706A4`, `Q-2026-01E18A-V2`, `QUO_2026_05_10_01E18A_V2_(R3,200.00)_Cash.pdf`.
3. EFT quote generated after approved test update of `ORD-2026-01E18A` from `Cash` to `EFT`: `DOC-2026-45F259`, `Q-2026-01E18A-V3`.
4. EFT totals verified: subtotal `R3,200.00`, VAT `R480.00`, total `R3,680.00`.
5. EFT Drive metadata verified as `application/pdf`.
6. `ORDER_DOCUMENTS` row verified for the EFT quote.
7. `ORD-2026-01E18A` now has `Payment_Method = EFT` after the approved EFT test.

## Phase 2.4 Invoice Generation Tests

Phase 2.4 first live invoice generation test completed on 2026-05-10:

1. `POST /api/orders/<order_id>/invoice` was added.
2. Missing-order smoke test returned `400` with `Order not found.`
3. Draft-order smoke test returned `400` with `Invoice can only be generated for Approved or Completed orders.`
4. `ORD-2026-01E18A` was promoted from `Draft | Pending` to `Approved | Approved` for the invoice test and logged in `ORDER_STATUS_LOG`.
5. Invoice generated from latest non-voided quote `Q-2026-01E18A-V3`.
6. Result document: `DOC-2026-EC0265`, `INV-2026-01E18A`, version `1`.
7. Generated file: `INV_2026_05_10_01E18A_V1_(R3,680.00)_EFT.pdf`.
8. Drive file ID: `1w5peZn-imS-t0p7BAwTd2fIWWGPg2Dgq`.
9. Totals verified: subtotal `R3,200.00`, VAT `R480.00`, total `R3,680.00`.
10. `ORDER_DOCUMENTS` row was appended and verified.
11. Drive metadata was verified as `application/pdf`.

## Phase 2.5 Document Delivery Tests

Phase 2.5 must use the approved test conversation only until the delivery workflow is signed off:

- Chatwoot test conversation: `1742`
- Test order: `ORD-2026-01E18A`
- Test quote: `DOC-2026-45F259`, `Q-2026-01E18A-V3`
- Test invoice: `DOC-2026-EC0265`, `INV-2026-01E18A`

Pre-check:

1. Import `docs/04-n8n/workflows/1.5 - outbound-document-delivery/workflow.json` into n8n.
2. Configure the Google Drive credential on `Google Drive - Download PDF`.
3. Configure the Chatwoot API token/credential on `HTTP - Chatwoot Send Attachment`.
4. Confirm the workflow production webhook URL is configured in backend env as `DOCUMENT_DELIVERY_WEBHOOK_URL`.

Test steps:

1. Direct webhook smoke test sends the generated PDF to `conversation_id = 1742`.
2. Confirm Chatwoot conversation `1742` received the correct PDF attachment and message text.
3. Backend send endpoint test uses `POST /api/order-documents/<document_id>/send` with `conversation_id = 1742`.
4. Confirm backend marks `ORDER_DOCUMENTS.Document_Status = Sent` only after n8n returns `success = true` and `sent = true`.
5. Confirm `Sent_At` and `Sent_By` are populated.
6. Confirm no real customer conversation receives the Phase 2.5 test document.

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
