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

### 1.2 Add Customer Cancel Action - Implemented, Needs Live Verification

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
- needs live Google Sheets verification using the operations checklist

### 1.3 Harden Release Behavior

Required outcome:

- release should be safe to call more than once
- release should not affect unrelated orders
- cancelled/invalid lines should not remain reserved
- reserved count must match real reserved lines

### 1.4 Add Lifecycle Guards

Required outcome:

- completed orders cannot be rejected/cancelled casually
- cancelled orders cannot be approved
- reserved/approved orders must handle state rollback safely

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

Rule:

Do not redesign the app before the backend order behavior is safe.

## Phase 5: Broader Workflow Improvements

Only after order stability:

- improve Sam order context
- improve AUTO reply quality where still needed
- fix and enable `1.3 - Media Tool`
- improve Telegram cleanup for human escalation
- expand monitoring and operational runbooks

## Current First Build Task

Finish verification for:

**Phase 1.2 - Add Customer Cancel Action**

Phase 1.1 reject behavior is implemented and live-verified.

For Phase 1.2, test:

- backend customer cancel endpoint/action
- `Order_Status = Cancelled`
- `Approval_Status = Not_Required`
- `Payment_Status = Cancelled`
- linked lines released/cancelled
- `ORDER_MASTER.Reserved_Pig_Count = 0`
- `ORDER_STATUS_LOG` entry exists
- `SALES_AVAILABILITY` recovers
