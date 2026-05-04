# Next Steps

## Purpose

Defines the approved build order from this point forward.

## Core Rule

Stabilize live order behavior before expanding features or polishing the app.

Orders are the profit section. They must be reliable before the system grows.

## Phase 1: Order Lifecycle Stabilization

Goal: make reject, cancel, release, and reservation state safe.

### 1.1 Fix Reject Behavior - Complete

Required outcome:

- rejecting an order updates header status
- linked reserved order lines are released/cancelled
- reserved pigs become available again through the sheet/formula chain
- `ORDER_STATUS_LOG` records the rejection
- Sam/web app receive a clear backend result

Current status:

- backend code cancels linked non-cancelled/non-collected lines
- backend code resets `Reserved_Pig_Count` to `0`
- backend code blocks completed orders from rejection
- live Google Sheets verification passed
- `SALES_AVAILABILITY` recovers correctly
- `ORDER_STATUS_LOG` entry is written

### 1.2 Add Customer Cancel Action - Complete And Live-Verified

Required outcome:

- add a backend cancel action/endpoint
- use `Order_Status = Cancelled`
- use `Approval_Status = Not_Required`
- use `Payment_Status = Cancelled`
- release/cancel linked lines
- write `ORDER_STATUS_LOG`
- expose through `1.2 - Order Steward` only after backend behavior is working

Current status:

- backend route `POST /api/orders/<order_id>/cancel` is implemented
- backend code cancels linked non-cancelled/non-collected lines
- backend code resets `Reserved_Pig_Count` to `0`
- backend code blocks completed orders from cancellation
- backend code keeps already rejected orders from being converted to customer-cancelled
- backend behavior was live-verified for line cancellation, reserved count recovery, availability recovery, and status log writing
- `1.2 - Order Steward` now exposes `cancel_order`
- `1.0 - Sam Sales Agent` now has guarded `CANCEL_PENDING`, `CANCEL_ORDER`, and `CLEAR_PENDING` routes
- two-turn Chatwoot cancellation is live-verified
- Chatwoot attribute preservation through escalation and human reply is live-verified
- cancellation after escalation is live-verified

### 1.2c Sync Order Lines After Draft Creation - Complete And Live-Verified

Required outcome:

- complete first-turn order requests create `ORDER_MASTER`
- if `requested_items[]` exists, the new draft immediately syncs matching `ORDER_LINES`
- Sam replies only after the draft and requested line sync path have completed
- no Merge node deadlock is introduced
- sync failure has a safe reply path and does not silently drop the customer

Current status:

- `1.0 Set - Draft Order Payload` sends `action = create_order_with_lines` when `order_state.requested_items[]` is non-empty
- `1.0` still owns routing only; it no longer contains the superseded Option A post-create sync branch
- `1.2 - Order Steward` owns the atomic create + sync branch
- `1.2 Code - Format Create With Lines Result` returns `success = true` only when both create and sync succeed
- live WhatsApp-to-Sheets verification passed on 2026-04-29 with `ORD-2026-879091`
- `ORDER_MASTER` had the new Draft order and `ORDER_LINES` had 3 matching Draft / Not_Reserved rows
- Sam referenced the order ID in the final reply on rerun

Follow-up, separate from Fix C:

- slim the Sales Agent prompt payload with a dedicated reply-context node so Sam receives only the fields needed for customer wording

### 1.3 Capture Payment Method Before Approval — Complete And Live-Verified

Manual prerequisites confirmed:
- `ORDER_MASTER` column Y = `Payment_Method` — added manually.
- `Sales_HumanEscalations` column S = `WebPaymentMethod` — added manually.

Required outcome:

- Sam asks the customer for Cash or EFT as part of order finalization, before offering to send for approval
- Payment method is stored on `ORDER_MASTER` via backend `PATCH /api/master/orders/<order_id>` — this is the source of truth
- Payment method is mirrored to Chatwoot `custom_attributes.payment_method` after backend success so future turns can read it without a backend lookup
- `Code - Normalize Incoming Message` in `1.0` reads `payment_method` from Chatwoot custom_attributes alongside `order_id`, `order_status`, and `pending_action`
- Payment method capture routes through the existing `ENRICH_EXISTING_DRAFT` path — no new Switch branch needed
- `Code - Build Enrich Existing Draft Payload` is updated to include `payment_method` when present
- All Chatwoot attribute write nodes in `1.0` and `1.1` must be audited and updated to include `payment_method` in their full-object snapshot before import — see `CHATWOOT_ATTRIBUTES.md`

Current status:

- backend `PATCH /api/master/orders/<order_id>` accepts `payment_method = Cash|EFT`
- backend writes `ORDER_MASTER.Payment_Method`
- backend rejects `payment_method` changes once the order is beyond `Draft`
- `1.0` detects `Cash` and `EFT`, routes through the existing enrich/update path, and mirrors `payment_method` to Chatwoot after backend success
- new `HTTP - Set Conversation Context After Update` writes the full Chatwoot snapshot after update/enrich paths
- `1.1` preserves `payment_method` through human reply release using `Sales_HumanEscalations.WebPaymentMethod`
- live verification passed on 2026-04-29 for Cash, EFT, next-turn readback, cancel-pending preservation, backend lock guard, no-draft handling, and escalation preservation

### 1.4 Wire Send For Approval From Sam — Complete And Live-Verified

Required outcome:

- Sam checks for active draft, at least one order line, and payment method before routing
- if any required field is missing, Sam tells the customer what is needed before proceeding
- `1.0` adds a `SEND_FOR_APPROVAL` branch to `Code - Decide Order Route`
- `1.0` calls `1.2` with `action=send_for_approval`
- `1.2 send_for_approval` branch calls backend `POST /api/orders/<order_id>/send-for-approval`
- backend validates: `Order_Status = Draft`, at least one ORDER_LINE, `Payment_Method` set, `customer_name` set, `collection_location` set
- `1.0` writes updated `order_status` to Chatwoot custom_attributes after backend confirms
- Sam tells the customer the order has been sent for approval — Sam does NOT say it is approved
- backend errors must return a customer-safe reply path in n8n; Sam must not go silent if a backend safety guard returns `400`

Current status:

- backend `send_order_for_approval` now validates: `Order_Status = Draft` (single clear check), `Payment_Method = Cash|EFT`, `Customer_Name` non-empty, `Collection_Location` non-empty, at least one non-cancelled `ORDER_LINE`
- backend returns clear `ValueError` messages for each guard that fails; route returns `400` with the message
- `1.2 HTTP - Send for Approval` has `neverError: true` so `400` responses are handled as data, not exceptions
- `1.2 Set - Format Send for Approval Result` returns conditional `order_status` (`Pending_Approval` on success, `Draft` on failure), conditional `approval_status`, and `backend_success`/`backend_error` fields
- `1.0 Code - Build Order State` detects `send_for_approval_intent` from customer phrases (send for approval, submit order, finalise order, confirm order, etc.)
- `1.0 Code - Decide Order Route` adds SEND_FOR_APPROVAL route: fires when `send_for_approval_intent + has_existing_draft + order_status = Draft + payment_method set`; falls through to REPLY_ONLY if payment method is missing (Sam sees the intent and asks for Cash/EFT)
- `1.0 Switch - Route Order Action` has new rule at index 6 for SEND_FOR_APPROVAL (REPLY_ONLY shifted to index 7)
- `1.0` new nodes: `Set - Build Send For Approval Payload` → `Call 1.2 - Send For Approval` → `HTTP - Set Chatwoot After Send Approval` → `Set - Restore Send For Approval Result` → `Merge - Final Replay Context` (index 1)
- Chatwoot write uses conditional order_status from 1.2 result — on success writes `Pending_Approval`, on failure preserves existing status
- all 4 new 1.0 nodes wired and JSON validated (83 nodes)
- Phase 1.4 bugfix expanded `send_for_approval_intent` detection to cover natural phrasings such as `send it for approval`, `send this through`, and `submit my order`
- live verification passed on 2026-04-30 with `ORD-2026-377DA3`: `send_for_approval_intent = true`, `order_route = SEND_FOR_APPROVAL`, `backend_success = true`, `order_status = Pending_Approval`, Chatwoot `order_status = Pending_Approval`, and Sam correctly said the order was sent for approval, not approved

Regression checks:

- missing `Payment_Method` should produce a customer-safe reply and no backend status change — failed in live test, then fixed and live re-tested 2026-05-04: routing stayed `REPLY_ONLY`, `reply_instruction` forced the payment-method question, Sam asked for Cash/EFT, backend was not called, and Draft status was preserved
- already `Pending_Approval` orders should not be submitted again — passed in live regression
- backend `400` guard failures should return a customer-safe reply rather than silence — passed in live regression 2026-05-04: backend rejected missing `Collection_Location`, Sam asked for the collection location, and did not claim the order was sent

Phase 1.4 fix applied and live re-tested 2026-05-04 — approval preflight block:

- `Code - Decide Order Route` now detects `send_for_approval_intent = true` with `sendForApprovalReady = false` and sets `reply_instruction` before the item reaches the Sales Agent
- missing-fields list is built from local checks; currently checks `payment_method`; future checks (no draft, wrong status) can be added in the same block
- when `payment_method` is missing: `reply_instruction = "INSTRUCTION: ... Ask exactly one question: Cash or EFT?"`
- order_route remains `REPLY_ONLY`; backend is not called; order_status is not changed; Draft is preserved
- `REPLY_ONLY` block in Sales Agent system message updated to honour `ReplyInstruction` as a hard override (mirrors the same rule already in the `SEND_FOR_APPROVAL` block)
- debug fields added: `debug_approval_preflight_blocked`, `debug_approval_missing_fields`
- no new Switch branches added
- backend `400` failures on the `SEND_FOR_APPROVAL` path are handled through `backend_success = false`, `backend_error`, and `reply_instruction`, preserving `Draft` status and producing a customer-safe reply

### 1.5 Lifecycle Guards — Complete And Live-Verified

Required outcome:

- backend rejects `Payment_Method` updates once `Order_Status` is `Pending_Approval` or later (`update_order` / `PATCH` master order)
- Sam-side routing in `1.0` checks `order_status` before sending `send_for_approval` — does not call backend if status is already `Pending_Approval`, `Approved`, `Cancelled`, or `Completed`
- completed orders cannot be cancelled or rejected without deliberate admin action (`reject_order` and `cancel_order` block `Completed`)
- cancelled orders cannot be re-approved (`approve_order` only accepts `Pending_Approval`, so `Cancelled`, `Draft`, and other statuses are rejected)
- reserved orders handle state rollback safely when cancel or reject is applied (reject/cancel line cleanup and `Reserved_Pig_Count` reset)

Follow-up deferred to later phases (not part of Phase 1.5 closure):

- approval auto-reservation — **Phase 1.8** after **Phase 1.6**; until then reservation stays a separate manual step (web app or workflow calling `POST /api/orders/<order_id>/reserve`)
- post-Phase 1.6: optional `approve_order` then reserve with `reserve_warning` on partial failure — **Phase 1.8**
- customer notification after approval/rejection — **Phase 1.9** (outbound n8n + webhook), not Sam `1.0`

Current status:

- backend `approve_order()` restricted to `Pending_Approval` only — live-verified 2026-05-04 (Draft cannot be approved via API; `Pending_Approval` approves successfully)
- backend payment method lock beyond `Draft` — implemented (see Phase 1.3 verification)
- Sam `send_for_approval` guarded to `Draft` — in place with Phase 1.4 regressions live-verified
- reject and customer-cancel paths block `Completed` and cancel/release linked lines as documented

### 1.6 Harden Reserve And Release Behavior

Required outcome:

- reserve order lines should handle larger/multi-line orders without partial silent failure
- release should be safe to call more than once
- release should not affect unrelated orders
- cancelled/invalid lines should not remain reserved
- reserved count must match real reserved lines
- backend/web app should return a clear success/failure summary for each line
- if approval auto-reserves lines, reserve behavior must be hardened before or as part of that change

Current status — **live-verified** (operator checklist 2026-05-05):

- `reserve_order_lines` refactored: eligibility checks skip `Cancelled`/`Collected` lines, lines with no `Pig_ID`, and noop already-reserved lines; all ORDER_LINES mutations applied in one `batch_update_rows_by_id` call; response includes `line_results` (per-line action/reason), `changed_count` (rows written), and `warning` when some lines were skipped; `success = false` + HTTP 422 when nothing could be reserved
- `release_order_lines` refactored: only clears `Reserved_Status` where `Reserved`; only reverts `Line_Status` from `Reserved` to `Draft` for active (non-Cancelled) lines; `Collected` lines are skipped; idempotent (second call returns all noops); `Reserved_Pig_Count` set from actual post-release count via `_count_reserved_lines`; response includes `line_results` and `changed_count`
- `order_routes.py`: reserve route returns HTTP 422 when `success = false`; `errors` field present for UI consumption
- Docs updated: `API_STRUCTURE.md`, `ORDER_LOGIC.md`

Verification notes (six tests):

- Mixed lines: reserve showed combined `warning` (terminal skips + no pig); two lines reserved as expected (UI summary: Reserved 2, Draft 1).
- Second reserve: no visible/UI delta — consistent with all eligible lines already reserved (`noop`, `changed_count = 0`).
- Release: success message; lines returned to draft-style summary (e.g. Draft 3; grower count unchanged).
- Second release: unchanged state — idempotent release.
- All-ineligible order: customer-safe `errors` message; order header counts remained consistent; HTTP 422 path confirmed.
- `SALES_AVAILABILITY` correct after release.

Manual verification checklist:

- [x] Order with 5 lines (2 cancelled, 1 no pig, 2 valid) → reserve → `line_results` has 5 entries; `changed_count = 2`; `warning` mentions 3 skipped; `reserved_pig_count = 2`
- [x] Call reserve again on same order → all 2 valid lines noop; `changed_count = 0`; `success = true`
- [x] Release → `line_results` shows 2 released, 3 noop/skipped; `reserved_pig_count = 0`; ORDER_MASTER count updated
- [x] Call release again → all noop; `changed_count = 0`; `success = true`; no sheet corruption
- [x] Order with no eligible lines (all cancelled) → reserve → `success = false`; HTTP 422; `errors` present
- [x] `SALES_AVAILABILITY` recovers reserved pigs after release

### 1.7 Slim Sales Agent Reply Payload

Required outcome:

- add a dedicated reply-context shaping node before `Ai Agent - Sales Agent`
- remove raw Chatwoot webhook data, large debug fields, and sync internals from Sam's prompt
- keep only customer context, order action, order ID/status, backend success, sync success, slim order state, and reply instruction
- preserve full diagnostic data in earlier workflow nodes

### 1.8 Approval Auto-Reservation

Required outcome:

- implement only after Phase 1.6 proves reserve/release is reliable and failure summaries are clear
- `approve_order` should set the approval state first, then attempt to reserve active order lines
- if reservation fails or partially fails, do not roll back the approval; write a warning to `ORDER_STATUS_LOG`, return `reserve_warning`, and let the admin web app surface the manual follow-up
- auto-reserve should ignore cancelled/inactive lines and report per-line outcomes clearly

### 1.9 Outbound Approval/Rejection Notifications

Required outcome:

- create a separate outbound n8n workflow, planned as `1.4 - Outbound Order Notification`, for backend-driven customer messages after human approval or rejection
- backend should call a new `ORDER_NOTIFICATION_WEBHOOK_URL` after successful `approve_order` or `reject_order`
- webhook delivery should be non-blocking with a short timeout; backend should log a warning if notification delivery fails, not fail the order transition
- notification workflow should find the Chatwoot conversation from stable stored data, preferably `ConversationId` on `ORDER_MASTER`
- before building the workflow, add/store `ConversationId` on `ORDER_MASTER` at draft creation time and define the exact approval/rejection message text
- decide whether rejection notifications include the rejection reason from the web app or use a generic message

## Phase 2: Quote And Invoice Generation

Goal: backend generates quote and invoice documents. n8n delivers them only.

### 2.1 Design Document Schema

Required outcome:

- define what fields appear on a quote (order ID, customer name, line items with ex-VAT unit price, quantity, line total, VAT amount, grand total, payment method, collection location, quote number, quote date)
- define what fields appear on an invoice (same as quote plus invoice number, approval date)
- define numbering format for quotes and invoices (sequential, stored in a backend counter or dedicated sheet)
- define output format (PDF preferred) and storage/retrieval path
- document VAT calculation rule: `EFT` orders add 15% on top of ex-VAT line totals; `Cash` orders show ex-VAT totals as final
- confirm `ORDER_LINES.Unit_Price` is stored at line creation time — if not, add it before quote generation is built

### 2.2 Backend Quote Endpoint

Required outcome:

- backend endpoint generates quote document for a given `order_id`
- uses `ORDER_MASTER.Payment_Method` to determine VAT treatment
- uses stored `ORDER_LINES.Unit_Price` (ex-VAT) for line calculations
- locks and stores the VAT rate on the quote record at generation time
- returns document URL or file reference

### 2.3 Backend Invoice Endpoint

Required outcome:

- backend generates invoice after order is approved
- uses the VAT rate locked on the corresponding quote, not recalculated
- returns document URL or file reference

### 2.4 n8n Delivery

Required outcome:

- `1.0` or a new workflow calls the quote/invoice endpoint after the relevant status event
- delivers the document to the customer via Chatwoot

## Phase 3: Daily Order Summary

Goal: scheduled operational overview of current order state.

### 3.1 Backend Report Endpoint

Required outcome:

- `GET /api/reports/daily-summary` returns counts and lists grouped by status: new drafts, drafts missing payment method, pending approval, approved, cancelled today, completed today, orders needing attention
- endpoint is independently testable
- n8n reads only from this endpoint, not from sheets directly

### 3.2 n8n Scheduled Delivery

Required outcome:

- n8n scheduled workflow fires daily (configurable time)
- calls backend summary endpoint
- formats output and sends to Telegram or email
- MVP fallback: n8n reads `ORDER_OVERVIEW` directly while backend endpoint is built — document as temporary

## Phase 4: Requested Item Sync Stabilization

Goal: make Sam's order-line sync reliable.

### 4.1 Fix Split Item Sync

Required outcome:

- `primary_1`, `primary_2`, and future split keys remain stable
- male/female split requests write all expected rows
- repeated sync does not duplicate rows
- old lines are released/cancelled before replacement

### 4.2 Define Partial Match Behavior

Required outcome:

- partial stock matches are returned clearly
- Sam does not confirm a complete update when backend only partially matched stock
- line totals must match requested quantity before success is treated as complete

### 4.3 Validate `intent_type` And `status`

Required outcome:

- either enforce these fields in backend sync or remove them from the required contract
- avoid fields that look important but do nothing

## Phase 5: Safe Order Review For Sam

Goal: let Sam understand saved order state without uncontrolled sheet access.

Preferred direction:

- add backend/Order Steward review action
- backend reads the relevant order data
- backend filters the result for Sam
- Sam answers based on backend-confirmed order truth

Possible actions:

- `review_order`
- `find_customer_orders`
- `get_active_customer_order_context`

## Phase 6: Web App Order Usability

Goal: make the app useful for daily order operations.

Focus areas:

- order list clarity
- order detail clarity
- visible line/reservation state
- clear approve/reject/cancel buttons
- order detail actions must match backend rules: show approve/reject when `Order_Status = Pending_Approval`, reserve/release when appropriate; avoid forcing ops through OOM SAKKIE workflows when parity with API is intended
- safe release/reserve controls
- useful logs/history
- clear success/failure messages
- less manual debugging
- short progress/status messaging for background actions such as reserve, release, reject, and cancel

Rule:

Do not redesign the app before the backend order behavior is safe.

## Phase 7: Broader Workflow Improvements

Only after order stability:

- improve Sam order context
- improve AUTO reply quality where still needed
- fix and enable `1.3 - Media Tool`
- improve Telegram cleanup for human escalation
- expand monitoring and operational runbooks

## Phase 8: Breeding Board Improvements — Completed 2026-05-02

### 8A Optional Pen Movement On Add Mating — Complete

- `GET /api/pig-weights/breeding-options` now returns `current_pen_id` and `current_pen_name` for each sow and boar.
- `/master/add-mating` form shows sow and boar current pen after selection, and optional `Move sow to pen` / `Move boar to pen` dropdowns populated from `GET /api/pig-weights/pens`.
- `POST /api/pig-weights/master/matings` accepts optional `sow_move_to_pen_id` and `boar_move_to_pen_id`.
- Backend calls `_write_movement_if_needed()` for each; skips write if target equals current pen or is empty.
- Movement rows are written to `LOCATION_HISTORY` with `reason = "Moved during mating log"`, `moved_by = "Mating Form"`.

### 8B Move To Farrowing / Assume Pregnant Action — Complete

- New endpoint: `POST /api/pig-weights/master/matings/<mating_id>/assume-pregnant`
- Updates `MATING_LOG`: `Pregnancy_Check_Date = today`, `Pregnancy_Check_Result = Pregnant`, `Mating_Status = Confirmed_Pregnant`, `Outcome = Pregnant`, `Updated_At = today`.
- Blocked for matings with status `Farrowed`, `Cancelled`, or `Closed`.
- Optional: if `target_pen_id` is supplied, writes sow movement row to `LOCATION_HISTORY` with `reason = "Moved to farrowing pen"`.
- Does NOT create a litter. Litter creation remains via Add Litter.
- `/matings` Breeding Board shows a "Move to Farrowing / Assume Pregnant" button on all eligible open mating cards (not Farrowed/Cancelled/Closed, no linked litter). Clicking opens an inline form with a pen dropdown (farrowing pens listed first). On confirm, POSTs to the endpoint and reloads the board.

### 8C Needs Action Now — No Litter After 3 Weeks Trigger — Complete

- In `matings.js`, when `is_overdue_farrowing = "Yes"` and no `linked_litter_id` and no `actual_farrowing_date` and `daysToFarrowing < -21`, the board classifies the record as `Needs Action Now` with action text `"No litter after 3 weeks — review"`.
- Movement guidance text explains the situation: days past expected farrowing, check if she has farrowed or if repeat service is needed.

### 8D Not Yet Built — Mark Not Pregnant / Repeat Service

When a sow has been in a farrowing pen too long with no litter, the next action is to mark her as not pregnant and return to repeat service. This is not yet built. When implemented:

- `POST /api/pig-weights/master/matings/<mating_id>/mark-not-pregnant`
- Updates `MATING_LOG`: `Pregnancy_Check_Result = Not_Pregnant`, `Mating_Status = Repeat_Service`, `Outcome = Repeat_Required`, `Updated_At = today`.
- Optionally moves sow back to a service pen.
- Available only for `Confirmed_Pregnant` matings with no litter and no actual farrowing date.

## Phase 9: Pig, Weight, And Reporting Improvements

Only after live order stability unless the operational need becomes urgent.

### 9.1 New Litter Defaults And Weaning Reminder

Required outcome:

- new `PIG_MASTER` rows generated from a litter should default `Purpose = Unknown`
- animals with `Purpose = Unknown` must not appear as for-sale stock
- once animals are weaned, surface a reminder to assign purpose: `Grow_Out`, `Sale`, or `Breeding`

### 9.2 Pig Dropdown Usability

Required outcome:

- pig-related dropdowns should show tag number and pen name, not only pen ID
- tag numbers should display as three digits where appropriate: `001`, `010`, `090`, `100`

### 9.3 Weight Form Context

Required outcome:

- beside `Move to Pen (Optional)`, show the current pen as read-only helper context

### 9.4 Weight Report

Required outcome:

- after weights are entered, allow the user to generate a weekly weight report
- include summaries, grouped totals, pen counts, and useful decision-making commentary
- this covers post-entry reporting only; pre-weighing handwritten capture is the separate Phase 9.6 printable sheet

### 9.5 Dashboard Sold This Month Audit

Required outcome:

- verify how `SOLD THIS MONTH` is calculated
- reconcile the April mismatch where the dashboard showed 20 but the expected sold count was 40

### 9.6 Printable Farm Operation Sheets

Required outcome:

- add a web-app page for printable farm operation sheets, likely `/print-sheets`
- first template: weekly weight sheet used before animals are weighed
- allow the user to choose which animals appear on the sheet: all active pigs, by pen/camp, by purpose, for-sale animals, or grow-out/sale animals
- printed sheet must be human-readable for farm workers and must hide internal IDs such as `Pig_ID`
- include: `Tag Number`, `Vorige Gewig Datum`, `Vorige Gewig`, blank `Nuwe Gewig`, current `Kamp`, blank `Nuwe Kamp`, and blank `Notas`
- include total count and a blank or user-selected weighing date at the top of the sheet
- default sorting should support the real farm workflow, preferably grouped by current pen/camp and then tag number
- support laptop and phone browser printing with print-friendly CSS, with save-to-PDF as a natural browser option
- read from existing system truth only during print generation; do not write to Google Sheets when creating a printable sheet
- keep this separate from Phase 9.4: printable sheets are for handwritten field capture before weights are entered, while weight reports summarize data after weights are entered

Follow-up idea:

- after the printable sheet is useful, consider a bulk weight entry page that follows the same row order so handwritten weights can be entered quickly without searching for each pig individually

## Phase 10: Farm Operating System Integration

Goal: bring Sam, Oom Sakkie, the web app, backend modules, weather logging, Synsynk solar data, n8n workflows, and Google Sheets into one documented operating-system structure.

Timing rule:

- do not start this umbrella integration until Sam/order behavior is stable enough that expanding the system will not hide existing sales bugs

Required outcome:

- document every major workflow and platform under one system map
- define ownership for each module: sales, farm operations, pig records, worker assistant, weather, solar, reporting, notifications, and admin web app
- create a workflow register showing trigger, purpose, inputs, outputs, reads, writes, dependencies, and risk level for each n8n workflow
- create data contracts for information passed between workflows, backend endpoints, web app pages, Google Sheets, and external systems
- set up Oom Sakkie documentation in the same style as Sam: workflow map, data flow, node responsibilities, protected logic, and input/output contracts
- ensure important operational writes go through backend-controlled logic where possible instead of direct workflow-to-sheet writes
- keep AI agents responsible for interpretation and wording, not hidden data ownership or business-rule enforcement
- document backend module boundaries for orders, pig operations, farm worker tasks, weather logging, solar data, reporting, and notifications
- add logging and audit expectations for customer actions, worker actions, web-app actions, backend actions, weather imports, and solar imports
- make the web app the visible control panel where possible so operators can understand system state without jumping between platforms

## Current Choice Point

Recently completed:

- Phase 1.1 reject behavior
- Phase 1.2 customer cancel through backend, `1.2`, and `1.0`
- Phase 1.2c first-turn create-with-lines via `create_order_with_lines`
- Phase 1.3 payment method capture — backend, `1.0`, `1.2`, `1.1`, Chatwoot mirror, and lock guard live-verified 2026-04-29
- Phase 1.4 send_for_approval happy path — backend validations, `1.2` neverError + conditional result, `1.0` intent detection + routing + 4 new nodes + Chatwoot write live-verified 2026-04-30
- Phase 1.4 bugfix — `sendForApprovalIntent` regex expanded to cover "send it for approval", "send this through", "submit it/this/my order", etc.; SEND_FOR_APPROVAL moved before UPDATE checks in route priority; Sales Agent prompt tightened so Sam never overstates on REPLY_ONLY; live re-verification passed 2026-04-30
- Phase 1.4 approval preflight and backend `400` regressions — fixed and live re-tested 2026-05-04; missing payment method now asks Cash/EFT without backend call; backend guard failures preserve Draft status and return a customer-safe missing-field reply
- Phase 1.5 lifecycle guards — Complete And Live-Verified 2026-05-04: `approve_order` only from `Pending_Approval`; payment lock beyond Draft; reject/cancel vs `Completed`; defer auto-reservation (1.8) and outbound notifications (1.9)
- Phase 1.6 reserve/release hardening — live-verified 2026-05-05: batch reserve/release, `line_results`, skip/warning semantics, idempotent release, ineligible-order 422 path, `SALES_AVAILABILITY` after release

Recommended next:

1. **Phase 1.8** (when ready) — Approval auto-reservation now has a hardened reserve path; implement per `NEXT_STEPS` §1.8, or prioritize polish/ops first
2. **Phase 6** — Web app order detail parity: expose approve/reject/reserve/release per backend lifecycle so ops matches workflow capability
3. **Phase 1.7** — Slim Sales Agent reply payload

Pick the next item deliberately before implementation so docs, workflow exports, and tests stay aligned.
