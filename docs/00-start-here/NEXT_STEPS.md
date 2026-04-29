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

### 1.3 Harden Reserve And Release Behavior

Required outcome:

- reserve order lines should handle larger/multi-line orders without partial silent failure
- release should be safe to call more than once
- release should not affect unrelated orders
- cancelled/invalid lines should not remain reserved
- reserved count must match real reserved lines
- backend/web app should return a clear success/failure summary for each line

### 1.4 Add Lifecycle Guards

Required outcome:

- completed orders cannot be rejected/cancelled casually
- cancelled orders cannot be approved
- reserved/approved orders must handle state rollback safely

### 1.5 Slim Sales Agent Reply Payload

Required outcome:

- add a dedicated reply-context shaping node before `Ai Agent - Sales Agent`
- remove raw Chatwoot webhook data, large debug fields, and sync internals from Sam's prompt
- keep only customer context, order action, order ID/status, backend success, sync success, slim order state, and reply instruction
- preserve full diagnostic data in earlier workflow nodes

## Phase 2: Requested Item Sync Stabilization

Goal: make Sam's order-line sync reliable.

### 2.1 Fix Split Item Sync

Required outcome:

- `primary_1`, `primary_2`, and future split keys remain stable
- male/female split requests write all expected rows
- repeated sync does not duplicate rows
- old lines are released/cancelled before replacement

### 2.2 Define Partial Match Behavior

Required outcome:

- partial stock matches are returned clearly
- Sam does not confirm a complete update when backend only partially matched stock
- line totals must match requested quantity before success is treated as complete

### 2.3 Validate `intent_type` And `status`

Required outcome:

- either enforce these fields in backend sync or remove them from the required contract
- avoid fields that look important but do nothing

## Phase 3: Safe Order Review For Sam

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

## Phase 4: Web App Order Usability

Goal: make the app useful for daily order operations.

Focus areas:

- order list clarity
- order detail clarity
- visible line/reservation state
- clear approve/reject/cancel buttons
- safe release/reserve controls
- useful logs/history
- clear success/failure messages
- less manual debugging
- short progress/status messaging for background actions such as reserve, release, reject, and cancel

Rule:

Do not redesign the app before the backend order behavior is safe.

## Phase 5: Broader Workflow Improvements

Only after order stability:

- improve Sam order context
- improve AUTO reply quality where still needed
- fix and enable `1.3 - Media Tool`
- improve Telegram cleanup for human escalation
- expand monitoring and operational runbooks

## Phase 6: Pig, Weight, And Reporting Improvements

Only after live order stability unless the operational need becomes urgent.

### 6.1 New Litter Defaults And Weaning Reminder

Required outcome:

- new `PIG_MASTER` rows generated from a litter should default `Purpose = Unknown`
- animals with `Purpose = Unknown` must not appear as for-sale stock
- once animals are weaned, surface a reminder to assign purpose: `Grow_Out`, `Sale`, or `Breeding`

### 6.2 Pig Dropdown Usability

Required outcome:

- pig-related dropdowns should show tag number and pen name, not only pen ID
- tag numbers should display as three digits where appropriate: `001`, `010`, `090`, `100`

### 6.3 Weight Form Context

Required outcome:

- beside `Move to Pen (Optional)`, show the current pen as read-only helper context

### 6.4 Weight Report

Required outcome:

- after weights are entered, allow the user to generate a weekly weight report
- include summaries, grouped totals, pen counts, and useful decision-making commentary

### 6.5 Dashboard Sold This Month Audit

Required outcome:

- verify how `SOLD THIS MONTH` is calculated
- reconcile the April mismatch where the dashboard showed 20 but the expected sold count was 40

## Current Choice Point

Recently completed:

- Phase 1.1 reject behavior
- Phase 1.2 customer cancel through backend, `1.2`, and `1.0`
- Phase 1.2c first-turn create-with-lines through `create_order_with_lines`

Recommended next candidates:

1. Phase 1.3 Harden Reserve And Release Behavior
2. Phase 1.4 Add Lifecycle Guards
3. Phase 1.5 Slim Sales Agent Reply Payload
4. Phase 2.1 Fix Split Item Sync

Pick the next item deliberately before implementation so docs, workflow exports, and tests stay aligned.
