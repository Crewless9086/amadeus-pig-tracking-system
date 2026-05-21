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
- 2026-05-18 Phase 7.0 checkpoint:
  - Production pre-redeploy create-with-lines wrote `ORD-2026-D15B1E` with one active Female Grower `35_to_39_Kg` line but returned `500` and did not attach a quote document. Cleanup cancelled the order; final state was `Order_Status = Cancelled`, `Payment_Status = Cancelled`, active lines `0`, cancelled lines `1`, and active lookup for conversation `1774` returned `no_match`.
  - Current local workspace code against live Sheets/Drive passed with `ORD-2026-900422`: response `201`, `create_success = true`, `sync_success = true`, `complete_fulfillment = true`, auto quote `DOC-2026-B474FD` / `Q-2026-900422`, then cleanup cancelled the order and active lookup returned `no_match`.
  - Post-deploy production retest still returned `500`, but wrote `ORD-2026-CF8C38` and generated `Q-2026-CF8C38`. Cleanup cancelled the order; final state was `Order_Status = Cancelled`, `Payment_Status = Cancelled`, active lines `0`, cancelled lines `1`, and active lookup for conversation `1774` returned `no_match`.
  - Render logs confirmed Google Sheets `429` read quota at spreadsheet metadata fetch (`client.open(GOOGLE_SHEET_NAME)`) was causing the production `500`.
  - Google Sheets cache/retry fix prepared in `services/google_sheets_service.py`: reuse the gspread client, opened spreadsheet, and worksheet handles per process, and retry quota-related `APIError` calls with short backoff.
  - Final retest passed after deploying the Google Sheets cache/retry fix: `ORD-2026-BBF8B3` returned cleanly with `success = true`, `create_success = true`, `sync_success = true`, `complete_fulfillment = true`, one active Female Grower `35_to_39_Kg` line, and generated `DOC-2026-6B90C2` / `Q-2026-BBF8B3`.
  - Cleanup cancelled `ORD-2026-BBF8B3`; final state was `Order_Status = Cancelled`, `Payment_Status = Cancelled`, active lines `0`, cancelled lines `1`, and active lookup for conversation `1774` returned `no_match`.

### Split Male/Female Request

Payload shape:

- `primary_1` = male request
- `primary_2` = female request

Expected:

- both keys create/preserve rows
- quantities match request
- no duplicate active rows after repeated sync
- no missing female/secondary rows

Phase 4.1 parser/route checks:

1. `I want 3 grower pigs 20-24kg, 1 male and 2 females, Riversdale, next Sunday, Cash` must produce `requested_weight_range = 20_to_24_Kg`, `requested_sex = Any`, two `requested_items[]` rows, and route `UPDATE_HEADER_AND_LINES`.
2. `I want 3 grower pigs 30-34kg, 1 male and 2 females, Riversdale, next Sunday, Cash` must produce `requested_weight_range = 30_to_34_Kg`, not `2_to_4_Kg`.
3. A short confirmation such as `yes please` may hydrate the split from memory, but must still route `UPDATE_HEADER_AND_LINES` when valid `requested_items[]` are built.
4. Current live-stock guard from 2026-05-10: use `20-24kg` for a full exact 1 Male + 2 Female test; `30-34kg` had Female-only stock and should verify partial/no-match honesty instead.
5. First-turn `create_order_with_lines` must persist `ORDER_MASTER.Collection_Location`, `Payment_Method`, and `ConversationId`; this was live-verified on `ORD-2026-25CC0D` and the test draft was then cancelled.

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

Phase 4.2 regression:

1. Use a split request where one `requested_items[]` row has no matching pigs and another row can match exactly, for example the live-stock guard noted on 2026-05-10: Grower `30_to_34_Kg`, quantity 3, `primary_1` Male x1 and `primary_2` Female x2 when that band has no Male stock.
2. Confirm backend returns `success = true` for the completed sync call, but `complete_fulfillment = false`, `partial_fulfillment = true`, `fulfillment_status = partial`, `requested_total = 3`, `matched_total = 2`, and `unmatched_total = 1`.
3. Confirm `incomplete_items[]` includes `primary_1` with `match_status = no_match`, requested 1, matched 0, plus alternatives when available.
4. Confirm `1.2 - order-steward` passes the fulfillment fields through both direct sync and `create_order_with_lines`.
5. Confirm `1.0 - Sam-sales-agent-chatwoot` exposes `had_no_match`, `had_incomplete`, and `partial_stock_detail` in `StewardCompact`, and Sam asks one follow-up instead of saying all 3 are on the draft.

Live verification reference:

- 2026-05-10: `ORD-2026-011771` created through `1.0`/`1.2` using Chatwoot test conversation `1742`. Backend created two active `primary_2` Female rows only; direct live sync returned `complete_fulfillment = false`, `fulfillment_status = partial`, `requested_total = 3`, `matched_total = 2`, `unmatched_total = 1`, and `primary_1 = no_match`. Sam generated correct partial/no-match wording. The test draft was cancelled after verification and ended with `active_line_count = 0`.

### Requested Item Metadata Validation

Phase 4.3 regression:

1. Direct sync with a normal active requested item and either no `intent_type` or `intent_type = primary` should pass validation.
2. Direct sync with `intent_type = nearby_addon` and `status = active` should pass validation.
3. Direct sync with an unknown `intent_type` should return `400` with a clear validation error and should not alter order lines.
4. Direct sync with `status = inactive` should return `400` with a clear validation error and should not alter order lines.
5. Confirm n8n `1.0` only sends active requested items; inactive/cancelled items must be omitted, not sent with a non-active status.

Live verification reference:

- 2026-05-11: Temporary Charl N draft `ORD-2026-07F5C8` was created with `ConversationId = 1742`. Valid direct sync with `intent_type = primary` and `status = active` passed validation and returned `success = true`; no lines were created because Grower `30_to_34_Kg` Male had no exact stock match. Invalid direct sync with `status = inactive` returned `400`; invalid direct sync with `intent_type = made_up` returned `400`. Final inspection showed no active lines or documents. The test draft was cancelled and ended with `active_line_count = 0` and `reserved_pig_count = 0`.

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

## Phase 5.2 Active Customer Order Lookup Tests

Backend endpoint: `GET /api/orders/active-customer-context`

Regression checks:

1. Missing `order_id`, `conversation_id`, and `customer_phone` returns `400`.
2. Exact active `order_id` returns `lookup_status = single_match` and a safe `order_context`.
3. Exact terminal `order_id` returns `lookup_status = terminal_order` and no active context.
4. Phone/conversation lookup with one active match returns `single_match`.
5. Phone/conversation lookup with multiple active matches returns `multiple_matches` with short summaries only.
6. No-match lookup returns `lookup_status = no_match`.
7. Response must not include the full `/api/orders` list, raw sheet rows, pig IDs, or tag numbers.
8. `1.0` should call the lookup only when no `ExistingOrderId` is present and the message is about an existing/saved order, cancellation, quote, or invoice.
9. `1.0` must not call the lookup for normal new sales messages such as "I want 2 piglets."
10. If `ExistingOrderId` is present, `1.0` must keep using `get_order_context` instead of the fallback lookup.
11. `HTTP - Get Conversation Messages` must build the Chatwoot URL from normalized `AccountId` and `ConversationId`; do not depend on `conversation.messages[0].account_id` or `conversation.messages[0].conversation_id`.
12. `1.2` `Switch - Route by Action` output `Get Active Customer Order Context` must use left value `={{ $json.action }}`, matching the other action branches.
13. When `conversation_id` is available, `1.0` should send that as the lookup key and leave `customer_phone` blank; phone is a fallback only when conversation ID is unavailable.
14. Backend lookup priority must be exact `order_id`, then exact `conversation_id`, then phone fallback.

Local verification reference:

- 2026-05-11: `ORD-2026-BDEFCE` returned `single_match` with 6 active draft lines grouped as 4 Female and 2 Male Young Piglets in `2_to_4_Kg`.
- 2026-05-11: phone lookup for `447388223114` returned `multiple_matches` for `ORD-2026-BDEFCE` and `ORD-2026-CEF70A`.
- 2026-05-11: `1.0` local JS checks confirmed "What is on my order?" with no existing order ID sets `should_active_customer_lookup = true`; "I want 2 piglets" does not; and an existing order ID keeps fallback lookup disabled.
- 2026-05-11: clean conversation `1774` first live run exposed the Chatwoot history URL ID-source issue. The `1.0` export was corrected to use normalized IDs before retest.
- 2026-05-11: `1.2` switch branch syntax was corrected from `={{ .action }}` to `={{ $json.action }}` before the next retest.
- 2026-05-11: conversation `1774` plus phone `447388223114` now returns `single_match` for `ORD-2026-8B7FC8`; phone-only still returns the expected multiple-match disambiguation.

Live verification reference:

- 2026-05-11: clean Chatwoot conversation `1774` with no `order_id` resolved to temporary order `ORD-2026-8B7FC8`.
- Sam replied with one specific draft order: 1 male piglet, `5_to_6_Kg`, Riversdale collection, `R400`.
- The temporary order was cancelled after verification. `ORD-2026-8B7FC8` now has `Order_Status = Cancelled`, one cancelled line, and `reserved_pig_count = 0`.
- After cleanup, `GET /api/orders/active-customer-context?conversation_id=1774` returns `lookup_status = no_match`.

## Phase 5.3 Sam Order-Review Wording Tests

Export readiness checks:

1. `1.0 - Sam-sales-agent-chatwoot` Sales Agent system prompt includes `ORDER REVIEW RESPONSE RULES`.
2. Current-order review replies must use backend/steward context first.
3. A single active match must produce a reply about that order only.
4. Multiple active matches must produce one disambiguation question, not a guessed order.
5. No active match must ask for an order reference and must not invent an order.
6. Draft wording must not say approved, confirmed, reserved, held, booked, or secured.
7. Pending Approval wording must say pending/submitted, not approved.
8. Approved wording may say approved only when backend context confirms it.
9. "What is on my order?" and "How many pigs did I order?" must summarize active/non-cancelled line quantities only.
10. "What is still missing?" must mention only fields inferred from context, or ask one focused follow-up if unclear.
11. Quote/invoice follow-up must not invent document links or say a document was sent without document context.
12. All five live prompts below must trigger active-order lookup when no `ExistingOrderId` is present and a conversation ID or phone is available.

Live prompts:

1. "What is on my order?"
2. "How many pigs did I order?"
3. "Is my order approved?"
4. "What is still missing?"
5. "Can you send my old quote/invoice again?"

Live verification reference:

- 2026-05-11: temporary Charl N order `ORD-2026-DDFEE6` was created on conversation `1774` with 1 male Young Piglet, `5_to_6_Kg`, Cash, Riversdale, `R400`.
- All five prompts above were accepted by the live workflow and project owner confirmed the replies were good.
- The temporary order was cancelled after verification. `ORD-2026-DDFEE6` now has `Order_Status = Cancelled`, one cancelled line, and `reserved_pig_count = 0`.
- After cleanup, `GET /api/orders/active-customer-context?conversation_id=1774` returns `lookup_status = no_match`.

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

Phase 2.5 live verification completed on 2026-05-10:

1. `1.5 - Outbound Document Delivery` was imported/configured in n8n.
2. Google Drive credential was configured for Shared Drive PDF download.
3. Chatwoot API key was configured for attachment send.
4. Production webhook URL: `https://charln.app.n8n.cloud/webhook/order-document-delivery`.
5. Direct webhook smoke test sent quote `DOC-2026-45F259`, `Q-2026-01E18A-V3`, to Chatwoot `conversation_id = 1742` and returned `success = true`, `sent = true`.
6. Direct webhook smoke test did not mark `ORDER_DOCUMENTS` as sent, as expected.
7. Backend endpoint test sent invoice `DOC-2026-EC0265`, `INV-2026-01E18A`, to Chatwoot `conversation_id = 1742`.
8. Backend endpoint returned `200`, `success = true`, `delivery_webhook_sent = true`, and `document_status = Sent`.
9. `ORDER_DOCUMENTS` verified `DOC-2026-EC0265` as `Document_Status = Sent`, `Sent_By = Codex Phase 2.5 Backend Test`, and `Sent_At = 10 May 2026 08:06`.

Regression checks for future edits:

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

## Phase 2.6 Web App Document Controls Tests

Phase 2.6 repo checks:

1. `GET /api/orders/<order_id>` returns `documents[]` from `ORDER_DOCUMENTS`.
2. Order detail page shows editable order header fields.
3. Payment method is editable only while the order is `Draft`; backend remains the final lock.
4. Order detail page shows generated documents with type, ref, status, total, payment method, created date, Drive link, and sent state.
5. `Generate Quote` calls `POST /api/orders/<order_id>/quote` and refreshes the document list after success.
6. `Generate Invoice` is disabled until the order is invoice-eligible and an active quote exists; backend remains the final guard.
7. Document `Send` requires a Chatwoot conversation ID and asks for confirmation before calling `POST /api/order-documents/<document_id>/send`.
8. Live read-only API check for `ORD-2026-01E18A` returned four documents from `ORDER_DOCUMENTS`.
9. Order summary is compact and shows operational totals/status at a glance.
10. Document rows are compact by default and expand for full details/actions.
11. Order line rows are compact by default and expand for full details/edit controls.
12. Order totals shown in the web app must not use `ORDER_OVERVIEW.Final_Total` when that formula includes cancelled lines; use latest document total for payable amount and `active_line_total` for active line value.

Browser verification still required:

1. Open `/orders/ORD-2026-01E18A`.
2. Confirm the Documents section renders all existing quote/invoice rows.
3. Confirm the invoice row shows `Sent`.
4. Confirm the quote rows show `Generated`.
5. Confirm Drive links open the PDFs.
6. Do not click `Send` on a real customer conversation unless explicitly approved.

## Phase 3.1 Daily Summary Endpoint Tests

Phase 3.1 live read-only verification completed on 2026-05-10:

1. `GET /api/reports/daily-summary?date=2026-05-10` returned HTTP `200`.
2. Response returned `success = true` and `report_date = 2026-05-10`.
3. Response contained all expected sections: `new_drafts`, `drafts_missing_payment_method`, `pending_approval`, `approved`, `cancelled_today`, `completed_today`, and `orders_needing_attention`.
4. Counts from the live check were: approved `2`, cancelled_today `0`, completed_today `0`, drafts_missing_payment_method `16`, new_drafts `1`, orders_needing_attention `17`, pending_approval `0`.
5. Invalid date test `?date=not-a-date` returned HTTP `400` with a clear validation error.
6. Endpoint reads through backend services; n8n should call this endpoint in Phase 3.2 instead of reading Google Sheets directly.

## Phase 3.2 Daily Summary n8n Tests

Pre-check:

1. Import `docs/04-n8n/workflows/1.6 - daily-order-summary/workflow.json`.
2. Configure `Telegram - Send Daily Summary` with the approved Telegram credential.
3. Confirm the Telegram target chat is the approved admin chat `5721652188`.
4. Confirm `HTTP - Get Daily Summary` calls `https://amadeus-pig-tracking-system.onrender.com/api/reports/daily-summary`.

Manual test:

1. Run `Manual Trigger - Test Summary`. - Passed 2026-05-10.
2. Confirm the workflow returns a backend `success = true` summary. - Passed 2026-05-10.
3. Confirm the Telegram message arrives. - Passed 2026-05-10.
4. Confirm the message includes all count sections and a short `Needs Attention` list when applicable. - Passed 2026-05-10.
5. Confirm n8n does not read Google Sheets directly. - Passed by workflow inspection.

Fix note:

- Initial Telegram test failed because Telegram entity parsing could not handle dynamic text containing underscores. The workflow now sends with `parse_mode = HTML`, escapes dynamic text, and formats reasons without underscores.

Schedule test:

1. Activate the schedule now that the manual test message is approved.
2. Confirm the schedule time is `16:00 Africa/Johannesburg`.
3. Confirm the next scheduled execution sends one Telegram message only.

## Web App Order Tests

After backend behavior is safe, test the app for usability:

- order list shows useful status at a glance
- order detail shows lines and reservation state clearly
- reserve/release actions show clear progress/result messages
- reject/cancel buttons are understandable and safe
- logs/history are visible enough for debugging
- failed actions show helpful errors
- app reduces manual work instead of increasing it

### Phase 6.1 Order Detail Action Parity

Repo checks completed 2026-05-17:

1. `node --check static/js/orderDetail.js` passed.
2. Flask app import passed.
3. `/order/<order_id>` has a `Cancel Order` button wired to `POST /api/orders/<order_id>/cancel`.
4. Order action buttons disable while an order action request is running.
5. Order action messages prefer backend `message`, preserve reserve/release `changed_count`, and append `warning` / `reserve_warning`.

Browser verification still required:

1. Draft order: reserve, release, send-for-approval, cancel, and add-line controls are visible; approve/reject/complete are hidden.
2. Pending Approval order: approve, reject, release, and cancel are visible; send-for-approval and complete are hidden.
3. Approved order: release, cancel, and complete are visible; approve/reject/send-for-approval are hidden.
4. Cancelled or Completed order: order-level action buttons and add-line form are hidden.
5. Confirm approve/reject/cancel/complete prompts appear before backend calls.
6. Use only a safe temporary order for destructive actions.

### Phase 6.2 Orders List Usability

Repo checks completed 2026-05-17:

1. `node --check static/js/orders.js` passed.
2. Flask test client returned the updated `/orders` template.
3. Local dev server was restarted and serves the updated `/orders` page.
4. Orders page now uses the same summary/filter/card pattern as Sales Availability.

Owner acceptance 2026-05-17:

- Phase 6.2 is accepted for now.
- Owner will make notes during live use if further polish is needed.

Future browser/live notes to watch:

1. `/orders` defaults to the Active tab.
2. Draft, Pending Approval, Approved, Completed, Cancelled, and All tabs show the expected groups.
3. Search finds order ID, customer, phone, conversation ID, request details, location, and notes.
4. Source, payment method, and collection location filters work with the active tab.
5. Clear Filters returns to the Active tab with all filters empty.
6. Cards remain readable on mobile and desktop.

## Web App Breeding Board Tests

The `/matings` page is an operational view for mating and movement planning. It reads from mating overview data and writes only through explicit confirmed action buttons.

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
14. For an eligible open mating, confirm `Move to Farrowing / Assume Pregnant` opens an inline form, optionally moves to a farrowing pen, and updates the mating only after confirmation.
15. For an eligible `Confirmed_Pregnant` mating with no linked litter and no actual farrowing date, confirm `Mark Not Pregnant / Repeat Service` opens an inline form.
16. For real active farm records, first test the backend endpoint with `dry_run: true` and confirm it returns planned updates without changing `MATING_LOG` or `LOCATION_HISTORY`.
17. Confirm `Mark Not Pregnant / Repeat Service` can optionally move the sow to a non-farrowing pen and writes `MATING_LOG` as `Pregnancy_Check_Result = Not_Pregnant`, `Mating_Status = Repeat_Service`, `Outcome = Repeat_Required`.
18. Confirm the repeat-service action is not shown or is blocked for matings with a linked litter, actual farrowing date, or non-`Confirmed_Pregnant` status.

Live result:

- 2026-05-20: Passed on real farm data. Baby's mating `MAT-2026-1565CF` was marked `Pregnancy_Check_Result = Not_Pregnant`, `Mating_Status = Repeat_Service`, `Outcome = Repeat_Required`, `is_open = No`, with no linked litter and no unintended pen move.
- 2026-05-20: New Baby/Prince mating `MAT-2026-9EFC4E` was created open and linked to the correct animals in `Kraam Saal 05`. The full-month formula date parser fix was deployed and live-verified: the API returns expected check `2026-06-09` and expected farrowing `2026-09-10`.

## Litter Creation Tests

Phase 9.1A:

1. Prefer the next real litter entry for live verification; do not create artificial litter data only for this check unless explicitly approved.
2. Confirm `save_new_litter` creates the expected number of `PIG_MASTER` piglet rows.
3. Confirm each litter-generated piglet row has `Animal_Type = Piglet`, `Status = Active`, `On_Farm = Yes`, `Source = Born_on_Farm`, and `Purpose = Unknown`.
4. Confirm `Purpose = Unknown` piglets do not appear as available-for-sale stock.
5. Confirm repeated creation logic does not duplicate piglet rows for an existing `Litter_ID`.

Live result:

- 2026-05-20: Passed on real farm data. `LIT-2026-9E4A` created 11 Lolly piglets and `LIT-2026-EB92` created 8 Shupe piglets. Direct `PIG_MASTER` verification confirmed `Animal_Type = Piglet`, `Status = Active`, `On_Farm = Yes`, `Source = Born_on_Farm`, and `Purpose = Unknown` for every generated row.

## Litter Attention Dashboard Tests

Phase 9.1B:

1. Confirm `GET /api/pig-weights/dashboard` returns `litter_attention`.
2. Confirm `litter_attention.count` includes litters where `LITTER_OVERVIEW.Needs_Attention = Yes`.
3. Confirm weaned litters with active piglets appear as `Weaned - review purpose`.
4. Confirm quiet active litters are not included.
5. Confirm `/` renders the `Litter Attention` section.
6. Confirm each reminder links to `/litter/<litter_id>`.
7. Confirm the litter detail page loads from `GET /api/pig-weights/litter/<litter_id>` and does not call the obsolete `/detail` API path.
8. Confirm opening the dashboard does not write to Google Sheets.

## Pig Dropdown Usability Tests

Phase 9.2A:

1. Confirm `GET /api/pig-weights/parent-options` includes `current_pen_name` for breeding mothers/fathers where the pen exists.
2. Confirm `GET /api/pig-weights/pigs` includes `current_pen_name` for active pigs where the pen exists.
3. Confirm Add Litter mother/father dropdown labels show tag number plus pen name, with pig ID as secondary context.
4. Confirm Add Mating sow/boar dropdown labels show tag number plus pen name, with pig ID as secondary context.
5. Confirm Weight Entry pig dropdown labels show tag number plus pen name, with pig ID as secondary context.
6. Confirm numeric-only tag numbers display as three slots, for example `001`, `010`, `099`, `120`.
7. Confirm dropdown order follows the tag/name display order rather than `PIG_ID`.
8. Confirm form submissions still send `pig_id` values, not display labels.

Phase 9.2B:

1. Open `/pigs`.
2. Confirm numeric-only pig tags display as three slots, for example `001`, `010`, `099`, `120`.
3. Confirm the list order is numeric-aware and useful for farm scanning.
4. Search for a raw tag such as `1` and confirm the matching padded tag appears.
5. Search for a padded tag such as `001` and confirm the same pig appears.
6. Search by `PIG_ID` and confirm the matching pig appears.
7. Click a pig card and confirm it opens the correct pig profile.

Local result:

- 2026-05-21: `node --check static/js/pigList.js` passed.
- 2026-05-21: Focused frontend contract tests passed.
- 2026-05-21: Full local unittest suite passed at 166 tests.
- 2026-05-21: Deployed and owner-confirmed; `/pigs` tag display is much better.

## Weight Form Context Tests

Phase 9.3:

1. Open `/pig-weights`.
2. Confirm the helper below `Moved To Pen (Optional)` says to select a pig first before a pig is selected.
3. Select a pig with a current pen.
4. Confirm the helper shows the selected pig's current pen name and pen ID.
5. Change the selected pig and confirm the helper updates.
6. Use the pen filter and confirm the helper remains correct for the selected pig or resets when the selected pig is no longer available.
7. Save a weight with no movement and confirm no movement is logged.
8. Save a weight with a target pen only when intentionally testing movement; confirm the payload still sends `moved_to_pen_id` and not the display helper text.

Live result:

- 2026-05-20: Deployed and owner-confirmed on `/pig-weights`; current-pen helper displays correctly beside `Moved To Pen (Optional)`.

Phase 9.3B weight form UX:

1. Open `/pig-weights`.
2. Confirm `New Weight (kg)` no longer shows browser spinner controls where the browser supports hiding them.
3. Focus the `New Weight (kg)` field, scroll the mouse wheel over it, and confirm the value does not change accidentally.
4. Confirm a `Save Weight` button appears directly after the required weight/date section.
5. Confirm the lower `Save Weight` button still appears after optional notes.
6. Save a normal weight and confirm both buttons use the same saving/disabled behavior and the payload is unchanged.

Local result:

- 2026-05-21: `node --check static/js/pigWeights.form.js` passed.
- 2026-05-21: Focused frontend contract tests passed.
- 2026-05-21: Full local unittest suite passed at 165 tests.
- 2026-05-21: Deployed and owner-confirmed; weight form UX looks better.

## Weight Report Tests

Phase 9.4:

1. Open `/weight-report`.
2. Confirm the report defaults to today's date for both `From` and `To`.
3. Confirm the page loads with either today's rows or a clear empty state.
4. Select a date range with known weight entries and run the report.
5. Confirm summary cards show total entries, unique pigs, average weight, average change, average growth/day, and loss flags.
6. Confirm pen summary groups rows by current pen.
7. Confirm detail rows show active/on-farm pigs only.
8. Confirm inactive/off-farm pigs are not included.
9. Confirm optional pen filter narrows the report.
10. Confirm invalid date ranges return a user-safe error.
11. Confirm `Print` opens browser print flow and the printed layout hides filters/buttons.
12. Confirm running the report does not write to Google Sheets.
13. Confirm duplicate same-day pig weights show a clear marker.
14. Confirm weight-loss rows appear in the dedicated `Loss Flags` section.
15. Confirm pen tables show pen names without pen IDs where names exist.
16. Confirm the date column hides on single-day reports and appears on multi-day reports.
17. Confirm notes are not shown in the detail table.
18. Confirm numeric pig tags in report tables display as three digits, for example `001`, `010`, `099`.
19. Confirm report rows are ordered by pen and then numeric pig tag order.
20. Future sortable-header check: when implemented, confirm `Pig`/tag and `Pen` headers toggle ascending/descending order while the default remains pen-grouped.

Live result:

- 2026-05-20: Deployed and owner-confirmed on `/weight-report`; owner confirmed the 9.4C1 refined report is usable.
- 2026-05-20: 9.4C2 duplicate prevention deployed and owner-tested working; report tag formatting follow-up implemented locally and local tests passed.
- 2026-05-20: Report tag formatting deployed and owner-confirmed; numeric pig tags display correctly on `/weight-report`.

Phase 9.4C2 duplicate prevention:

1. Select a pig and date with no existing weight and confirm save works normally.
2. Try saving another weight for the same pig and same date.
3. Confirm the backend blocks the first duplicate save with a duplicate warning.
4. Confirm the web app asks for explicit confirmation before adding another same-day weight.
5. Cancel the confirmation and confirm no new row is written.
6. Confirm the duplicate intentionally only in a controlled test case, not on live farm data unless needed.

## Dashboard Monthly Sales Tests

Phase 9.5:

1. Open the dashboard.
2. Confirm the Sales section shows `Sales Exits This Month`, `Livestock Exits`, `Slaughter Exits`, and `Meat Exits`.
3. Confirm `Sales Exits This Month` equals the combined livestock + slaughter + meat monthly exit count.
4. Confirm completed live pig orders still count under `Livestock Exits`.
5. Confirm pigs with `Status = Slaughtered` or abattoir/slaughter exit reasons count under `Slaughter Exits`.
6. Confirm future meat sale exits can be counted under `Meat Exits` without building the full meat-sales workflow yet.
7. Confirm old months do not leak into the current-month dashboard count.
8. Future 9.5B check: confirm the Sales section shows transaction count, pig/item count, and Rand value separately for total sales, livestock, slaughter, and meat once a transaction/value source exists.
9. Future 9.5B check: confirm Rand totals come from explicit sales/order/transaction value fields and are not inferred from pig count alone.
10. Future 9.5B check: confirm slaughter/abattoir sales have a clear sale record before Rand totals are shown.

Local result:

- 2026-05-20: Implemented locally and verified with dashboard/frontend focused tests plus full 127-test suite.
- 2026-05-20: Deployed/browser-visible; owner confirmed the stream cards are present and requested later count/value planning.
- 2026-05-21: 9.5B planning updated; Rand values remain blocked until explicit transaction/value source is defined.
- 2026-05-21: 9.5B1 wording cleanup implemented locally. `node --check static/js/dashboard.js`, focused dashboard/frontend tests, and full local unittest suite passed at 166 tests.
- 2026-05-21: 9.5B1 deployed and owner-confirmed; dashboard now uses `Exits` wording for sales stream counts.
- 2026-05-21: 9.5B2 planning captured; slaughter/abattoir Rand totals remain blocked until a transaction/value source exists.

## Printable Farm Operation Sheet Tests

Phase 9.6A:

1. Open `/print-sheets`.
2. Confirm the first available sheet is a weekly weight capture sheet.
3. Confirm the page is read-only and does not write to Google Sheets when opened or printed.
4. Confirm worker-facing print columns include `Tag Number`, `Vorige Gewig Datum`, `Vorige Gewig`, blank `Nuwe Gewig`, current `Kamp`, blank `Nuwe Kamp`, and blank `Notas`.
5. Confirm internal `Pig_ID` is not shown on the printed sheet.
6. Confirm rows default to active/on-farm pigs only.
7. Confirm rows are sorted by current pen/camp and then numeric tag number.
8. Confirm total row count and selected/default weighing date appear at the top.
9. Confirm browser print hides app navigation, filters, and buttons.
10. Confirm the printed layout is usable from laptop/desktop browser print and save-to-PDF.
11. Confirm labels are English.
12. Confirm the default shows all active/on-farm pigs and pen filtering can narrow to one or multiple pens.
13. Future 9.6B check: optional columns such as sex, stage, and purpose can be added only when selected.

Local result:

- 2026-05-20: Implemented locally and verified with `node --check static/js/printSheets.js`, focused route/frontend tests, and full 129-test suite.
- 2026-05-20: Deployed and owner-tested on `/print-sheets`; owner confirmed it is good for now.

## Phase 10A Planning Checks

Before starting Supabase setup or new integrations:

1. Confirm `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md` lists all major modules.
2. Confirm each module has a current data owner and target data owner.
3. Confirm first migration boundary is still orders/sales transactions unless owner deliberately changes it.
4. Confirm telemetry is treated separately from first order migration.
5. Confirm n8n direct sheet writes are identified before replacing them with backend APIs.
6. Confirm Supabase foundation requirements are understood before collecting secrets or importing data.

## Phase 10.1 Supabase Foundation Planning Checks

Before adding database dependencies, env vars, migrations, or connection code:

1. Confirm `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md` has been reviewed.
2. Confirm first migration boundary is orders/sales transaction data unless owner deliberately changes it.
3. Confirm telemetry/Sunsynk remains a separate review boundary.
4. Confirm backend is the only writer for the first database phase.
5. Confirm no browser Supabase anon key will be used before RLS policies exist.
6. Confirm n8n will call backend APIs rather than direct Supabase writes.
7. Confirm guided default: existing Supabase Pro project is used as foundation/staging first, with no production cutover.
8. Confirm guided default: plain SQL migrations live in `supabase/migrations/`.
9. Confirm guided default: add a harmless backend `/health/database` smoke endpoint.
10. Confirm backup/restore expectation before production data import.

Phase 10.1A local checks:

1. `GET /health/database` returns `503` and `status = not_configured` when `DATABASE_URL` is missing.
2. Failure responses do not include the connection string, database password, Supabase service-role key, anon key, customer data, or pig data.
3. `supabase/migrations/README.md` exists and confirms that no schema migration has started yet.
4. `requirements.txt` includes a Postgres driver for deployed Supabase connection tests.

Local result:

- 2026-05-21: Focused database tests passed.
- 2026-05-21: Full local unittest suite passed at 132 tests.
- 2026-05-21: Direct `/health/database` smoke returned `503` with `status = not_configured` and no secret data before `DATABASE_URL` is configured.

Phase 10.1A deployed checks, after Render env vars are added:

1. Render has `DATABASE_URL`, `SUPABASE_URL`, and `SUPABASE_PROJECT_REF`.
2. Render does not have `SUPABASE_SERVICE_ROLE_KEY` unless a later backend-admin feature requires it.
3. Render does not expose Supabase anon key to the browser.
4. `GET /health/database` returns `200`, `success = true`, `status = ok`, and harmless database timing/name fields only.

Deployed result:

- 2026-05-21: Owner verified `/health/database` returned `configured = true`, `database = postgres`, `status = ok`, `success = true`, and database UTC time.

Phase 10.1B baseline migration checks:

1. Confirm `supabase/migrations/202605210001_foundation_migration_log.sql` creates only `app_private.migration_log`.
2. Confirm it does not create orders, pigs, weights, matings, litters, weather, Sunsynk, irrigation, or customer tables.
3. Confirm backend route `GET /health/database/foundation` exists.
4. Before SQL is applied, the foundation route should fail safely.
5. After SQL is applied in Supabase SQL Editor, the foundation route should return `success = true`, `status = ok`, and migration ID `202605210001_foundation_migration_log`.

Local result:

- 2026-05-21: Focused database tests passed at 6 tests.
- 2026-05-21: Full local unittest suite passed at 135 tests.
- 2026-05-21: Migration contract test confirms the baseline SQL creates only the internal migration log and no business tables.

Deployed result:

- 2026-05-21: Owner ran the baseline SQL in Supabase SQL Editor.
- 2026-05-21: `/health/database/foundation` returned `success = true`, `status = ok`, migration ID `202605210001_foundation_migration_log`, and applied timestamp `2026-05-21T01:19:31.638474+00:00`.

## Phase 10.2 Order/Sales Schema Planning Checks

Before creating business tables:

1. Confirm `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md` has been reviewed.
2. Confirm the first boundary remains seven tables: `orders`, `order_lines`, `order_intakes`, `order_intake_items`, `order_documents`, `order_status_logs`, and `sales_pricing`.
3. Confirm pig, weight, breeding, weather, Sunsynk, irrigation, and `SALES_AVAILABILITY` remain outside the first boundary.
4. Confirm import remains dry-run/shadow first; no production cutover.
5. Confirm test-data exclusion rules before import planning.
6. Confirm open questions in the schema plan before writing the first business-table SQL migration.

Phase 10.2A empty schema checks:

1. Confirm `supabase/migrations/202605210002_create_order_sales_tables.sql` creates exactly the seven 10.2 boundary tables.
2. Confirm it does not create pig, weight, breeding, weather, Sunsynk, irrigation, `SALES_AVAILABILITY`, or import tables outside the approved boundary.
3. Confirm it inserts migration ID `202605210002_create_order_sales_tables` into `app_private.migration_log`.
4. Confirm backend route `GET /health/database/order-schema` exists.
5. After SQL is applied, confirm `/health/database/order-schema` returns `success = true`, `status = ok`, migration ID `202605210002_create_order_sales_tables`, and no missing tables.
6. Confirm current order routes still use Google Sheets until a later read/write cutover phase is approved.

Local result:

- 2026-05-21: Focused database tests passed at 9 tests.
- 2026-05-21: Full local unittest suite passed at 138 tests.

Deployed result:

- 2026-05-21: Owner ran the SQL migration in Supabase SQL Editor.
- 2026-05-21: `/health/database/order-schema` returned `success = true`, `status = ok`, migration ID `202605210002_create_order_sales_tables`, all seven expected tables found, and `missing_tables = []`.

Phase 10.2B import dry-run checks:

1. Confirm `scripts/order_sales_import_dry_run.py` reads Google Sheets only.
2. Confirm the dry-run report contains `writes_to_supabase = false`.
3. Confirm test customer `Charl N` is excluded.
4. Confirm child rows with excluded/missing parents are excluded and counted as link issues.
5. Confirm pricing rows require sale category, weight band, and price.
6. Confirm the live dry-run is run with `--summary-only` first.
7. Confirm no Supabase inserts or updates are performed.

Local result:

- 2026-05-21: Focused dry-run tests passed at 5 tests.
- 2026-05-21: Full local unittest suite passed at 143 tests.

Live dry-run result:

- 2026-05-21: Summary-only dry-run completed with `writes_to_supabase = false`.
- Included rows: `ORDER_MASTER = 26`, `ORDER_LINES = 103`, `ORDER_INTAKE_STATE = 27`, `ORDER_INTAKE_ITEMS = 7`, `ORDER_DOCUMENTS = 6`, `ORDER_STATUS_LOG = 62`, `SALES_PRICING = 21`.
- Main follow-up: `ORDER_STATUS_LOG` has 157 `missing_parent_order` rows and 111 `parent_order_excluded` rows; investigate before import mapping.

Phase 10.2B status-log diagnostic checks:

1. Confirm `scripts/order_status_log_diagnostic.py` reads only `ORDER_MASTER` and `ORDER_STATUS_LOG`.
2. Confirm it reports `writes_to_supabase = false` and `writes_to_sheets = false`.
3. Confirm it classifies logs into included candidate, missing order ID, missing parent order, and test parent order.
4. Confirm unlinked/test status logs are excluded from import unless the owner explicitly identifies specific rows as business history.

Local result:

- 2026-05-21: Focused diagnostic/dry-run tests passed at 7 tests.
- 2026-05-21: Full local unittest suite passed at 145 tests.

Live diagnostic result:

- 2026-05-21: Status-log diagnostic completed with `writes_to_supabase = false` and `writes_to_sheets = false`.
- Classification counts: `included_candidate = 62`, `missing_parent_order = 157`, `test_parent_order = 111`, `missing_order_id = 0`.
- Import mapping rule: include only the 62 included-candidate status logs by default; exclude missing-parent/test-parent logs unless owner manually approves exceptions later.

Phase 10.2C payload mapping checks:

1. Confirm payload mapping still reports `writes_to_supabase = false` and `writes_to_sheets = false`.
2. Confirm only included rows are mapped to payload samples.
3. Confirm payloads include `source_sheet_row` and `import_batch_id = DRY_RUN_ONLY`.
4. Confirm phone raw/normalized, money, booleans, and JSON/list fields are represented.
5. Confirm payload samples are reviewed before any real insert script is built.

Local result:

- 2026-05-21: Focused payload/dry-run tests passed at 7 tests.
- 2026-05-21: Full local unittest suite passed at 147 tests.

Live payload sample result:

- 2026-05-21: Payload sample report completed with `writes_to_supabase = false` and `writes_to_sheets = false`.
- Mapped rows: `orders = 26`, `order_lines = 103`, `order_intakes = 0`, `order_intake_items = 0`, `order_documents = 6`, `order_status_logs = 62`, `sales_pricing = 21`.
- Review finding: some mapped orders are cancelled historical customer orders; review included order quality before building a real insert script.
- Owner decision update: first import should include completed real orders only, plus pricing reference data. Draft/pending/approved/cancelled/rejected history stays in Sheets unless manually approved later.

Completed-only payload result:

- 2026-05-21: Completed-only payload dry-run completed with `writes_to_supabase = false` and `writes_to_sheets = false`.
- Mapped rows: `orders = 3`, `order_lines = 53`, `order_intakes = 0`, `order_intake_items = 0`, `order_documents = 0`, `order_status_logs = 11`, `sales_pricing = 21`.
- Source exclusions: `not_completed_order = 23`, `test_customer_charl_n = 56`, `parent_order_excluded = 118` for order lines, and `missing_parent_order = 157` for status logs.
- Current pass condition: first real import script, if approved, must target this completed-only boundary and remain shadow-only until compared against Sheet-backed reads.

Phase 10.2D shadow import checks:

1. Confirm `scripts/order_sales_shadow_import.py` defaults to plan-only.
2. Confirm plan-only reports `writes_to_supabase = false` and `writes_to_sheets = false`.
3. Confirm apply mode requires explicit `--apply`.
4. Confirm apply mode requires `DATABASE_URL`.
5. Confirm apply mode uses import batch `IMPORT-20260521-COMPLETED-ORDERS-V1`.
6. Confirm insert/upsert order respects foreign keys: pricing, orders, lines, intakes, intake items, documents, status logs.
7. Confirm first apply, if approved, imports only the completed-order boundary.

Local result:

- 2026-05-21: Focused shadow-import/dry-run tests passed at 12 tests.
- 2026-05-21: Full local unittest suite passed at 152 tests.

Live plan-only result:

- 2026-05-21: Plan-only shadow import run completed with `writes_to_supabase = false` and `writes_to_sheets = false`.
- Payload counts matched the approved boundary: `orders = 3`, `order_lines = 53`, `order_intakes = 0`, `order_intake_items = 0`, `order_documents = 0`, `order_status_logs = 11`, `sales_pricing = 21`.

Apply result:

- 2026-05-21: Missing local `DATABASE_URL` attempt failed safely with `writes_to_supabase = false`.
- 2026-05-21: First real apply attempt failed safely with `NotNullViolation`; transaction rolled back.
- 2026-05-21: Timestamp normalization fix added and retested.
- 2026-05-21: Shadow import `--apply` succeeded with `writes_to_supabase = true` and `writes_to_sheets = false`.
- Imported/upserted counts: `orders = 3`, `order_lines = 53`, `order_intakes = 0`, `order_intake_items = 0`, `order_documents = 0`, `order_status_logs = 11`, `sales_pricing = 21`.

Verification result:

- 2026-05-21: `scripts/order_sales_shadow_import_verify.py` confirmed Supabase batch counts for `IMPORT-20260521-COMPLETED-ORDERS-V1`.
- Verified counts: `orders = 3`, `order_lines = 53`, `order_intakes = 0`, `order_intake_items = 0`, `order_documents = 0`, `order_status_logs = 11`, `sales_pricing = 21`.
- No backend read/write cutover has started.

Phase 10.2E shadow read comparison checks:

1. Confirm `scripts/order_sales_shadow_compare.py` reads Google Sheets and Supabase only.
2. Confirm it writes nothing to Google Sheets or Supabase.
3. Confirm it compares row counts, missing IDs, extra IDs, and selected business fields.
4. Confirm it returns `mismatch_count = 0` before any backend read cutover is discussed.

Local result:

- 2026-05-21: Focused compare/import tests passed at 19 tests.
- 2026-05-21: Full local unittest suite passed at 159 tests.

Live comparison result:

- 2026-05-21: `scripts/order_sales_shadow_compare.py` completed with `success = true`, `status = ok`, and `mismatch_count = 0`.
- Matched counts: `orders = 3`, `order_lines = 53`, `order_intakes = 0`, `order_intake_items = 0`, `order_documents = 0`, `order_status_logs = 11`, `sales_pricing = 21`.
- No backend read/write cutover has started.

Phase 10.2F read-only shadow endpoint checks:

1. Confirm endpoint is `GET /api/shadow/orders/<order_id>/compare`.
2. Confirm `/api/orders/<order_id>` is unchanged and still Sheet-backed.
3. Confirm response includes `writes_to_sheets = false` and `writes_to_supabase = false`.
4. Confirm an imported order returns `success = true`, `status = ok`, and `mismatch_count = 0`.
5. Confirm a missing shadow order returns a safe `404`, not a live-route fallback.

Local result:

- 2026-05-21: Focused shadow route/service tests passed at 32 tests.
- 2026-05-21: Full local unittest suite passed at 164 tests.
- 2026-05-21: Local API smoke for `GET /api/shadow/orders/ORD-2026-0B29D7/compare` returned HTTP 200, `success = true`, `status = ok`, and `mismatch_count = 0`.

Deploy result:

- 2026-05-21: Deployed endpoint check passed for `GET /api/shadow/orders/ORD-2026-0B29D7/compare`.
- Response returned `success = true`, `status = ok`, `mismatch_count = 0`, `writes_to_sheets = false`, and `writes_to_supabase = false`.
- No backend route cutover has started.

Phase 10.2G sales transaction extension planning checks:

1. Confirm `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md` contains a `10.2G Sales Transaction Extension Plan`.
2. Confirm the proposed future tables are `sales_transactions` and `sales_transaction_items`.
3. Confirm the model covers `Livestock`, `Slaughter`, and `Meat` streams without inferring Rand values from pig counts.
4. Confirm `sales_transactions` owns sale header, buyer/destination, money, payment, status, and audit fields.
5. Confirm `sales_transaction_items` owns linked pigs/items, weights, unit price, pricing basis, and line totals.
6. Confirm 10.2G is planning only: no SQL migration, backend route, dashboard Rand value, order cutover, or pig migration has started.
7. Confirm open decisions are reviewed before creating any SQL migration.

Planning result:

- 2026-05-21: 10.2G planning added to the Supabase schema plan.
- 2026-05-21: Current recommendation is to review fields first, then decide whether the next implementation slice is empty transaction tables plus a verifier.

Phase 10.2H sales transaction empty schema checks:

1. Confirm `supabase/migrations/202605210003_create_sales_transaction_tables.sql` creates exactly `sales_transactions` and `sales_transaction_items`.
2. Confirm it does not create pig, customer, weight, breeding, telemetry, deduction child, or dashboard tables.
3. Confirm constrained values exist for sale stream, sale status, payment status, item type, and pricing basis.
4. Confirm it inserts migration ID `202605210003_create_sales_transaction_tables` into `app_private.migration_log`.
5. Confirm backend route `GET /health/database/sales-transaction-schema` exists.
6. After SQL is applied, confirm `/health/database/sales-transaction-schema` returns `success = true`, `status = ok`, migration ID `202605210003_create_sales_transaction_tables`, and no missing tables.
7. Confirm current order/dashboard routes still use existing data sources until a later cutover phase is approved.

Local result:

- 2026-05-21: Focused database tests passed at 12 tests.
- 2026-05-21: Full local unittest suite passed at 169 tests.

Deploy result:

- 2026-05-21: Owner ran the SQL migration in Supabase SQL Editor.
- 2026-05-21: `/health/database/sales-transaction-schema` returned `success = true`, `status = ok`, migration ID `202605210003_create_sales_transaction_tables`, both expected tables found, and `missing_tables = []`.
- No backend/dashboard/order behavior changed.

Phase 10.2I read-only sales transaction API checks:

1. Confirm endpoint is `GET /api/sales-transactions`.
2. Confirm it reads Supabase only.
3. Confirm it returns `writes_to_sheets = false` and `writes_to_supabase = false`.
4. Confirm it supports optional `sale_stream = Livestock`, `Slaughter`, or `Meat`.
5. Confirm invalid `sale_stream` returns `400`.
6. Confirm no write/create/update/delete endpoint exists yet for sales transactions.
7. Confirm dashboard Rand totals are still not connected.

Local result:

- 2026-05-21: Focused sales transaction/database tests passed at 17 tests.
- 2026-05-21: Local route smoke without `DATABASE_URL` returned safe `503` / `not_configured`.
- 2026-05-21: Full local unittest suite passed at 174 tests.

Deploy result:

- 2026-05-21: `GET /api/sales-transactions` returned `success = true`, `status = ok`, `count = 0`, empty `sales_transactions`, and read-only source flags.
- No records, write form, dashboard Rand totals, or order automation were added.

Phase 10.2J sales transaction dry-run validator checks:

1. Confirm endpoint is `POST /api/sales-transactions/dry-run`.
2. Confirm a valid slaughter payload returns `success = true`, `status = ok`, and `mode = dry_run`.
3. Confirm the response calculates `gross_total`, `deductions_total`, `net_total`, `item_count`, and `pig_count`.
4. Confirm response source has `writes_to_sheets = false` and `writes_to_supabase = false`.
5. Confirm invalid payloads return `400` with validation errors.
6. Confirm no real create endpoint exists yet.
7. Confirm Supabase row count remains unchanged after dry-run tests.

Local result:

- 2026-05-21: Focused sales transaction tests passed at 8 tests.
- 2026-05-21: Local dry-run route smoke passed with a valid slaughter payload.
- 2026-05-21: Full local unittest suite passed at 177 tests.

Deploy result:

- 2026-05-21: Dry-run slaughter payload returned `success = true`, `mode = dry_run`, `gross_total = 1200`, `deductions_total = 100`, `net_total = 1100`, and both write flags remained false.
- No real create endpoint, sale IDs, dashboard Rand totals, order automation, or pig status changes were added.

Phase 10.2K controlled sales transaction create-flow planning checks:

1. Confirm first real write endpoint is planned as `POST /api/sales-transactions`.
2. Confirm first write scope is `Slaughter` only.
3. Confirm writes go to Supabase only and never to Google Sheets.
4. Confirm backend must generate `sale_id`, `sale_item_id`, `pig_count`, `gross_total`, `deductions_total`, and `net_total`.
5. Confirm header and items must write atomically in one database transaction.
6. Confirm duplicate pig protection blocks any `pig_id` already used in a non-cancelled sales transaction.
7. Confirm first write slice does not update `PIG_MASTER`, dashboard Rand totals, livestock order automation, meat sales, or a web form.
8. Confirm cancellation/void behavior is planned before live operational use.
9. Confirm real slaughter workflow is represented: `JC Slaghuis` as buyer/butcher, `Bartelsfontein` as abattoir/destination, optional carcass weight, bank transfer/EFT payment normally about two weeks later.
10. Confirm unpaid slaughter entries use `sale_status = Confirmed` and `payment_status = Unpaid`, then move to `Completed` / `Paid` only after payment is received.
11. Confirm VAT handling is not forgotten; structured VAT fields or a clear VAT basis must be decided before dashboard financial totals are treated as accounting-ready.
12. Confirm pig `S10` is not written as a real Supabase transaction until create/cancel behavior is proven and owner approves live use.

Planning result:

- 2026-05-21: 10.2K create-flow plan added to `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`.
- 2026-05-21: Real JC Slaghuis/Bartelsfontein slaughter workflow and S10 candidate note captured for 10.2K.

Local result:

- 2026-05-21: 10.2K1 backend create service and route implemented locally.
- 2026-05-21: Focused sales transaction tests passed at 15 tests.
- 2026-05-21: Local missing-config route smoke returned safe `503` with `writes_to_supabase = false`.
- 2026-05-21: Full local unittest suite passed at 184 tests.

Deploy result:

- 2026-05-21: 10.2K1 deployed.
- 2026-05-21: 10.2K2 synthetic write test created `SALE-2026-F17E16` for `PIG-TEST-102K2-20260521`.
- 2026-05-21: Readback through `GET /api/sales-transactions?sale_stream=Slaughter&limit=10` returned the synthetic transaction.
- 2026-05-21: Duplicate-pig protection returned `409 duplicate_pig` on a second create attempt for `PIG-TEST-102K2-20260521`.
- No real `S10` transaction has been written.
- 2026-05-21: 10.2K3 cancellation/void flow implemented locally.
- 2026-05-21: Focused sales transaction tests passed at 20 tests.
- 2026-05-21: Local missing-config cancel route smoke returned safe `503` with `writes_to_supabase = false`.
- 2026-05-21: Full local unittest suite passed at 191 tests.

Phase 10.2K3 deployed cancellation checks:

1. Cancel synthetic transaction `SALE-2026-F17E16` using `POST /api/sales-transactions/SALE-2026-F17E16/cancel`. Passed 2026-05-21.
2. Confirm response returns `status = cancelled`, `sale_status = Cancelled`, `payment_status = Cancelled`, and `writes_to_supabase = true`. Passed 2026-05-21.
3. Confirm `GET /api/sales-transactions?sale_stream=Slaughter&limit=10` shows `SALE-2026-F17E16` as cancelled. Passed 2026-05-21.
4. Confirm a new synthetic transaction can reuse `PIG-TEST-102K2-20260521` after cancellation. Passed 2026-05-21 with `SALE-2026-28EF1B`.
5. Cancel cleanup synthetic transaction `SALE-2026-28EF1B`. Passed 2026-05-21.
6. Confirm no real `S10` transaction is written until all cancellation checks pass. Passed 2026-05-21.

Deploy result:

- 2026-05-21: 10.2K3 deployed cancellation checks passed.
- 2026-05-21: Final readback shows synthetic slaughter transactions `SALE-2026-F17E16` and `SALE-2026-28EF1B` are both cancelled.
- No real `S10` transaction has been written.

## Phase 10.2L Internal Slaughter Sale Form Checks

Local result:

- 2026-05-21: Internal slaughter sale form implemented locally at `/sales/slaughter`.
- 2026-05-21: `node --check static/js/slaughterSale.js` passed.
- 2026-05-21: Focused frontend/sales tests passed at 27 tests.
- 2026-05-21: Local page smoke returned `200` and included `slaughterSale.js`.
- 2026-05-21: Full local unittest suite passed at 192 tests.

Deploy checks:

1. Open `/sales/slaughter`.
2. Confirm active pigs load in the pig dropdown.
3. Confirm recent slaughter transactions load and show cancelled synthetic rows.
4. Confirm defaults are `JC Slaghuis`, `Bartelsfontein`, `Unpaid`, `Confirmed`, and `EFT`.
5. Owner can then log real `S10` from the form when ready.
6. Confirm real `S10` appears in recent slaughter transactions after save.
7. Confirm Google Sheets are not written by the form.

## Phase 10.2L2 Slaughter Payment / Final Amount Update Checks

Local result:

- 2026-05-21: Payment/final amount update implemented locally.
- 2026-05-21: New route is `PATCH /api/sales-transactions/<sale_id>/payment`.
- 2026-05-21: `/sales/slaughter` now shows `Update Payment` for non-cancelled rows.
- 2026-05-21: `node --check static/js/slaughterSale.js` passed.
- 2026-05-21: Focused sales/frontend tests passed at 23 tests.
- 2026-05-21: Local missing-config update route smoke returned safe `503` with `writes_to_supabase = false`.
- 2026-05-21: Full local unittest suite passed at 200 tests.

Deploy checks:

1. Create a new synthetic slaughter transaction from `/sales/slaughter`.
2. Click `Update Payment` on the synthetic row.
3. Update final amount, payment status, sale status, and optional carcass weight.
4. Confirm the row reloads with the updated total and status.
5. Confirm update appends an audit note in Supabase.
6. Cancel the synthetic row after testing.
7. Do not update real `S10` payment/final amount until the synthetic update check passes.

Owner-pending note:

- 2026-05-21: Owner decided to park the payment/final amount test until the real JC Slaghuis value is known.
- Return to this checklist when the butcher payment/final amount is available.

## Phase 10.2L3 Slaughter Form UX Polish Checks

Local result:

- 2026-05-21: Added top save action, transaction search, sale-status filter, payment-status filter, clear filters action, filtered transaction count, and clearer status pills to `/sales/slaughter`.
- 2026-05-21: `node --check static/js/slaughterSale.js` passed.
- 2026-05-21: Frontend contract tests passed at 10 tests.
- 2026-05-21: Local page smoke for `/sales/slaughter` returned `200`.
- 2026-05-21: Full local unittest suite passed at 200 tests.

Deploy checks:

1. Open `/sales/slaughter`.
2. Confirm the top save button is visible after selecting sale date and pig.
3. Confirm transaction search filters recent rows by sale ID, buyer, status, payment, amount, or date.
4. Confirm sale-status and payment-status filters work.
5. Confirm `Clear Filters` resets the table.
6. Confirm create/cancel/update payment buttons still appear only where expected.
7. Confirm no multi-pig/batch behavior was introduced in this slice.

## Phase 10.2L4 Multi-Pig Slaughter Batch Planning Checks

Planning result:

- 2026-05-21: Multi-pig slaughter batch plan added to `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`.
- Batch model: one `sales_transactions` row per slaughter event, multiple `sales_transaction_items` rows for pigs.
- Payment date is required as a planned schema addition before final payment reporting.
- Batch total and optional per-pig amount support is recommended, but no automatic allocation rule has been approved.

Checks before implementation:

1. Confirm `payment_date` migration should be 10.2L4A.
2. Confirm whether the first multi-pig UI should include optional per-pig amounts or only a batch total.
3. Confirm payment date should be required when `payment_status = Paid`.
4. Confirm carcass-weight estimate behavior before showing any estimate in the UI.
5. Confirm paid-batch correction rule before allowing edits after payment.
6. Confirm synthetic two-pig batch test IDs before deployed testing.

## Phase 10.2L4A Payment Date Schema Checks

Local result:

- 2026-05-21: Migration `supabase/migrations/202605210004_add_sales_transaction_payment_date.sql` created locally.
- 2026-05-21: Backend verifier `GET /health/database/sales-payment-date-schema` created locally.
- 2026-05-21: Focused database tests passed at 15 tests.
- 2026-05-21: Local missing-config verifier smoke returned safe `503`.
- 2026-05-21: Full local unittest suite passed at 203 tests.

Deploy checks:

1. Deploy backend containing `/health/database/sales-payment-date-schema`.
2. Run `supabase/migrations/202605210004_add_sales_transaction_payment_date.sql` in Supabase SQL Editor.
3. Open `/health/database/sales-payment-date-schema`.
4. Confirm `success = true`, `status = ok`, migration ID `202605210004_add_sales_transaction_payment_date`, and `payment_date_column_found = true`.
5. Do not start 10.2L4B multi-item write testing until this verifier passes.

Deploy result:

- 2026-05-21: Owner ran the SQL migration in Supabase SQL Editor.
- 2026-05-21: `/health/database/sales-payment-date-schema` returned `success = true`, `status = ok`, migration ID `202605210004_add_sales_transaction_payment_date`, applied timestamp `2026-05-21T15:45:04.636332+00:00`, and `payment_date_column_found = true`.

## Phase 10.2L4B Backend Multi-Item Create Checks

Local result:

- 2026-05-21: Backend create path verified for one slaughter transaction header with multiple pig item rows.
- 2026-05-21: Validation now rejects duplicate `pig_id` values inside the same submitted batch before any database write.
- 2026-05-21: Existing Supabase duplicate-pig check remains in place for pigs already linked to non-cancelled sales transactions.
- 2026-05-21: Focused sales transaction create/dry-run/route tests passed at 17 tests.
- 2026-05-21: Full local unittest suite passed at 206 tests.

Deploy checks:

1. Deploy backend containing the 10.2L4B validation and create tests.
2. Confirm existing single-pig `/sales/slaughter` create behavior still works before using the multi-pig UI.
3. Confirm duplicate submitted pigs are rejected by dry-run/create before writing to Supabase.
4. Do not create a real multi-pig slaughter batch until 10.2L4C form support and 10.2L4E synthetic batch testing are complete.

## Phase 10.2L4C Form Multi-Pig Selector Checks

Local result:

- 2026-05-21: `/sales/slaughter` form changed from one fixed pig selector to repeatable pig rows under one slaughter batch.
- 2026-05-21: Each pig row captures pig, per-pig amount, optional carcass weight, and optional pig note.
- 2026-05-21: The form shows a calculated batch total from the pig rows and blocks duplicate selected pigs before submit.
- 2026-05-21: `node --check static/js/slaughterSale.js` passed.
- 2026-05-21: Focused frontend/sales tests passed at 27 tests.
- 2026-05-21: Local `/sales/slaughter` page smoke returned `200`.
- 2026-05-21: Full local unittest suite passed at 206 tests.

Deploy checks:

1. Deploy frontend/backend together.
2. Open `/sales/slaughter` and confirm one pig row appears by default.
3. Add a second pig row, choose two different synthetic/test pigs, and confirm the batch total updates.
4. Try selecting the same pig twice and confirm the form blocks submit before writing.
5. Do not use a real multi-pig slaughter batch until 10.2L4D payment update and 10.2L4E synthetic batch testing are complete.

## Phase 10.2L4D Payment Update With Batch Total/Payment Date Checks

Local result:

- 2026-05-21: Payment update accepts `payment_date` and requires it when `payment_status = Paid`.
- 2026-05-21: Header totals/payment/date/status update together.
- 2026-05-21: Single-pig updates still update the one item amount and optional carcass weight.
- 2026-05-21: Multi-pig batch updates do not auto-reallocate final batch totals across item rows.
- 2026-05-21: `/sales/slaughter` payment prompt now asks for final batch amount and payment date when marking Paid.
- 2026-05-21: `node --check static/js/slaughterSale.js` passed.
- 2026-05-21: Focused update/route/frontend tests passed at 25 tests.
- 2026-05-21: Local `/sales/slaughter` page smoke returned `200`.
- 2026-05-21: Full local unittest suite passed at 208 tests.

Deploy checks:

1. Deploy frontend/backend together.
2. Create only a synthetic two-pig slaughter batch in 10.2L4E.
3. Update the synthetic batch payment to `Paid` with a payment date.
4. Confirm the transaction header shows the final batch amount and paid status.
5. Confirm item rows were not silently reallocated.
6. Cancel the synthetic batch and confirm duplicate-pig protection releases those synthetic pigs after cancellation.

Deploy result:

- 2026-05-21: Deployed synthetic API test created two-pig batch `SALE-2026-17736A` using `PIG-TEST-L4E-A-20260521180640` and `PIG-TEST-L4E-B-20260521180640`.
- 2026-05-21: Active duplicate create was blocked with `409 duplicate_pig`.
- 2026-05-21: Payment update succeeded with final batch amount `2700`, `payment_status = Paid`, and `payment_date = 2026-05-21`.
- 2026-05-21: Multi-pig payment update returned `items_updated = 0`, confirming no automatic item reallocation.
- 2026-05-21: Synthetic batch `SALE-2026-17736A` was cancelled.
- 2026-05-21: Reuse batch `SALE-2026-0C9DE0` using the same synthetic pig IDs was created successfully after cancellation, proving duplicate-pig release.
- 2026-05-21: Reuse batch `SALE-2026-0C9DE0` was cancelled.
- 2026-05-21: Deployed `/sales/slaughter` page smoke passed and included the multi-pig row container plus batch total UI.

## Phase 10.3C Telemetry Power Schema Checks

Local result:

- 2026-05-21: First telemetry power migration added locally at `supabase/migrations/202605210005_create_telemetry_power_tables.sql`.
- 2026-05-21: Migration creates `telemetry_sources`, `power_readings_5min`, `power_latest_state`, and `telemetry_alerts`.
- 2026-05-21: Migration seeds source row `sunsynk-main-inverter`.
- 2026-05-21: Migration imports no telemetry readings and changes no Render logger or n8n workflow.
- 2026-05-21: Backend verifier added locally at `GET /health/database/telemetry-power-schema`.
- 2026-05-21: Focused database tests passed at 18 tests.
- 2026-05-21: Local missing-config verifier smoke returned safe `503`.
- 2026-05-21: Full local unittest suite passed at 211 tests.

Deploy checks:

1. Deploy backend containing `/health/database/telemetry-power-schema`.
2. Run `supabase/migrations/202605210005_create_telemetry_power_tables.sql` in Supabase SQL Editor.
3. Open `/health/database/telemetry-power-schema`.
4. Confirm `success = true`, `status = ok`, migration ID `202605210005_create_telemetry_power_tables`, and `missing_tables = []`.
5. Confirm `sunsynk_source.source_id = sunsynk-main-inverter`.
6. Do not change the Sunsynk Render logger or n8n `2.2` until this verifier passes.

Deploy result:

- 2026-05-21: `/health/database/telemetry-power-schema` returned `success = true`, `status = ok`, migration ID `202605210005_create_telemetry_power_tables`, all four expected tables found, and `missing_tables = []`.
- 2026-05-21: Seed source confirmed as `sunsynk-main-inverter`, `provider = sunsynk`, `source_type = power`, `stale_after_minutes = 15`.

## Phase 10.3D/10.3E Telemetry Ingest And Current Endpoint Checks

Local result:

- 2026-05-21: Ingestion decision documented: Render Sunsynk logger should call the Flask backend instead of writing directly to Supabase.
- 2026-05-21: `POST /api/telemetry/power/ingest` implemented locally and protected by `TELEMETRY_INGEST_API_KEY`.
- 2026-05-21: `GET /api/telemetry/power/current` implemented locally.
- 2026-05-21: Current endpoint missing-config smoke returned safe `503` with `status = not_configured`.
- 2026-05-21: Ingest endpoint missing-key smoke returned safe `503` with `status = ingest_key_not_configured`.
- 2026-05-21: Focused telemetry tests passed at 8 tests.
- 2026-05-21: Full local unittest suite passed at 219 tests.

Deploy checks:

1. Add `TELEMETRY_INGEST_API_KEY` to the Render backend environment.
2. Deploy backend containing the telemetry endpoints.
3. Open `GET /api/telemetry/power/current`; before first ingest it may return `status = unavailable`.
4. Send one safe synthetic Sunsynk payload to `POST /api/telemetry/power/ingest` with header `X-Amadeus-Telemetry-Key`.
5. Confirm ingest returns `success = true` and `source.writes_to_supabase = true`.
6. Re-open `GET /api/telemetry/power/current`.
7. Confirm it returns the latest synthetic state with source freshness and deterministic flags.
8. Do not update the Render Sunsynk logger until this deployed test passes.

Deploy result:

- 2026-05-21: Synthetic ingest returned `success = true`, `status = ok`, `source_id = sunsynk-main-inverter`, `reading_id = PWR-FEC6256BECB7`, and `source.writes_to_supabase = true`.
- 2026-05-21: `/api/telemetry/power/current` read back the synthetic state with battery `82%`, battery state `charging`, solar `3120 W`, load `1240 W`, grid state `not_using_grid`, generator state `off`, deterministic flags, and stale summary.
- 2026-05-21: Stale summary was expected because the synthetic timestamp was intentionally older than the 15-minute threshold.
- Rotate `TELEMETRY_INGEST_API_KEY` before wiring the real Render Sunsynk logger if the current test key was pasted into chat or logs.

## Phase 10.3F Sunsynk Logger Update Checks

Local result:

- 2026-05-21: Sunsynk logger updated locally to POST normalized readings to backend ingest when `AMADEUS_BACKEND_URL` and `TELEMETRY_INGEST_API_KEY` are set.
- 2026-05-21: Logger keeps Google Sheets as a transition mirror unless `GOOGLE_SHEETS_ENABLED=false`.
- 2026-05-21: Logger README added with required Render cron env vars.
- 2026-05-21: First Render cron recovery test failed in the Google Sheets mirror path with `gspread` 404; `/api/telemetry/power/current` still showed the old synthetic reading.
- 2026-05-21: Logger hardened locally so a successful backend ingest is not failed by a Google Sheets mirror error.
- 2026-05-22: Render cron source moved to the main `amadeus-pig-tracking-system` repo with root directory `external_sources/telemetry/sunsynk/amadeus-sunsynk-logger`; trailing-space root directory issue corrected.
- 2026-05-22: Render cron printed `backend_ingest_enabled = true`, `backend_ingest_success = true`, reading ID `PWR-49F0F62E4F21`, `google_sheets_written = true`, and `google_sheets_error = null`.
- 2026-05-22: `/api/telemetry/power/current` returned real fresh data with `data_age_minutes = 0`, `is_stale = false`, battery `47%`, battery state `discharging`, load `872 W`, no solar, no grid, and no generator.
- 2026-05-21: Syntax verification passed with `python -m py_compile`.

Deploy checks:

1. Update the Render cron service code for `amadeus-sunsynk-logger`.
2. Add Render cron env var `AMADEUS_BACKEND_URL=https://amadeus-pig-tracking-system.onrender.com`.
3. Add Render cron env var `TELEMETRY_INGEST_API_KEY` with the same rotated value used on the backend.
4. Set `GOOGLE_SHEETS_ENABLED=false` for the next recovery test unless the Google Sheets mirror name/access is fixed first.
5. Run/wait for one cron execution.
6. Confirm Render cron log reports `backend_ingest_enabled = true`, `backend_ingest_success = true`, and either `google_sheets_enabled = false` or `google_sheets_written = true`.
7. Confirm `/api/telemetry/power/current` returns a fresh reading with low `data_age_minutes`.
8. Do not update Oom Sakkie `2.2` until this deployed logger check passes.

Verified result:

- 2026-05-22: Passed. Oom Sakkie `2.2` can now be updated to use the backend current power endpoint.

## Phase 10.3G Oom Sakkie Power Tool Checks

Local result:

- 2026-05-22: `2.2 - Amadeus Sunsynk Sub-Agent` rebuilt as a deterministic backend current-power worker.
- 2026-05-22: `2.2` no longer contains `AI Sunsynk Agent`, `OpenAI Chat Model`, or Sunsynk Google Sheets tool nodes.
- 2026-05-22: `2.0 - OOM SAKKIE` `Sunsynk_Info_Tool` description updated to point to the backend/Supabase current-power path.
- 2026-05-22: Updated workflow JSON files parse successfully.
- 2026-05-22: Backend current-power endpoint returned fresh data before workflow import.

Live import/test checks:

1. Import `docs/04-n8n/workflows/2.2 - Amadeus Sunsynk Sub-Agent/workflow.json`.
2. Import `docs/04-n8n/workflows/2.0 - OOM SAKKIE - Amadeus Assistant Agent/workflow.json`.
3. In Telegram, ask Oom Sakkie: `What's the power like now?`
4. Confirm the answer returns quickly and includes battery, solar, load, grid, generator, and latest reading freshness.
5. Confirm the answer does not mention Google Sheets or workflows.
6. Ask a daily/last-24h power question.
7. Confirm the answer does not hang and clearly says daily/kWh/trend read models are not available in this slice yet.
8. If the answer works, mark 10.3G imported and live-verified.

## Google Sheets Checks

After any order change, inspect affected sheets/views:

- `ORDER_MASTER`
- `ORDER_LINES`
- `ORDER_STATUS_LOG`
- `PIG_OVERVIEW`
- `SALES_AVAILABILITY`
- `ORDER_OVERVIEW`

Formula sheets must not be manually edited to hide backend bugs.

## Sales Stock Formula Checks

Before testing Sam stock wording or requested-item sync:

1. Confirm `PIG_OVERVIEW.Is_Sale_Ready = Yes` requires `Purpose = Sale`.
2. Confirm `SALES_AVAILABILITY` contains only sale-ready pigs.
3. Confirm `SALES_STOCK_DETAIL`, `SALES_STOCK_SUMMARY`, and `SALES_STOCK_TOTALS` do not mix sale-ready totals with information-only rows in a way Sam can quote as available stock.
4. If `Newborn` rows remain visible, confirm their `Status` is `Not for Sale` and Sam treats them as informational only.
5. Confirm `Grow_Out`, `Unknown`, `Breeding`, `Replacement`, and `House_Use` animals are not counted as available-for-sale stock.

## Documentation Checks

Before closing a change, update any affected files under:

- `docs/02-backend/`
- `docs/03-google-sheets/`
- `docs/04-n8n/`
- `docs/06-operations/`
- `docs/00-start-here/`
