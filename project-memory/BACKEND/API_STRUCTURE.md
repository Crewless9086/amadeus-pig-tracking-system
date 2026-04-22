1. PURPOSE
This document defines:
All backend API endpoints (Flask)
How n8n interacts with the backend
Allowed operations per endpoint
Data contracts (input/output)
Safety rules to prevent data corruption
This is the single source of truth for:
👉 Backend ↔ n8n communication
👉 Order operations
👉 Pig reservation logic
👉 Data integrity
2. CORE PRINCIPLE
👉 Backend = Source of Truth
👉 n8n = Orchestrator (NOT decision maker)
2.1 Strict separation
Layer
Responsibility
n8n
decides WHAT should happen
Backend
executes HOW it happens safely
2.2 Hard rule
❌ n8n must NEVER:
directly edit Google Sheets
bypass backend logic
assign pigs manually
3. API DESIGN RULES
3.1 One responsibility per endpoint
Each endpoint must do ONE thing:
Plain text
create order
update order
reserve pigs
release pigs
NOT combinations.
3.2 Idempotency
Endpoints must be safe to call multiple times:
Plain text
Same request → same result → no duplicates
3.3 Validation first
Backend must validate:
required fields
order state
pig availability
BEFORE writing anything
3.4 No silent failure
Every endpoint must return:
JSON
{
  "success": true/false,
  "message": "...",
  "data": {...}
}
4. CORE ENDPOINTS
4.1 CREATE ORDER
Endpoint
Http
POST /master/orders
Purpose
Create new draft order
Input
JSON
{
  "customer_name": "Charl",
  "customer_phone": "+27...",
  "customer_channel": "WhatsApp",
  "requested_category": "Piglet",
  "requested_weight_range": "2_to_4_Kg",
  "requested_quantity": 6,
  "collection_location": "Riversdale",
  "collection_date": "2026-04-20"
}
Rules
Must generate ORD-YYYY-XXXXXX
Must set:
Plain text
Order_Status = Draft
Output
JSON
{
  "success": true,
  "order_id": "ORD-2026-ABC123"
}
4.2 UPDATE ORDER HEADER
Endpoint
Http
PATCH /master/orders/{order_id}
Purpose
Update order details without touching lines
Allowed fields
requested_quantity
requested_category
requested_weight_range
collection_location
collection_date
notes
Rules
❌ Must NOT:
create lines
assign pigs
change reservation
4.3 CREATE ORDER LINE
Endpoint
Http
POST /master/order-lines
Purpose
Create a single line item
Input
JSON
{
  "order_id": "ORD-2026-ABC123",
  "sale_category": "Piglet",
  "weight_band": "2_to_4_Kg",
  "sex": "Male",
  "quantity": 2
}
Output
JSON
{
  "success": true,
  "order_line_id": "OL-2026-XXXXXX"
}
4.4 UPDATE ORDER LINE
Endpoint
Http
PATCH /master/order-lines/{order_line_id}
Purpose
Update quantity or attributes
Rules
❌ Must NOT:
auto assign pigs
override reservation logic
4.5 DELETE ORDER LINE
Endpoint
Http
DELETE /master/order-lines/{order_line_id}
Purpose
Remove line and release pigs
Rules
👉 Must trigger:
Plain text
release reservation
4.6 RESERVE PIGS
Endpoint
Http
POST /orders/{order_id}/reserve
Purpose
Assign pigs to order lines
Logic
Backend must:
Fetch order lines
Fetch available pigs from SALES_AVAILABILITY
Match:
category
weight_band
sex
Assign pigs
Rules
Plain text
Available_For_Sale = Yes
AND Reserved_Status = Available
Output
JSON
{
  "success": true,
  "reserved_count": 6
}
4.7 RELEASE PIGS
Endpoint
Http
POST /orders/{order_id}/release
Purpose
Free all pigs linked to order
Action
Reset:
Plain text
Reserved_Status = Available
Reserved_For_Order_ID = ""
4.8 SEND FOR APPROVAL
Endpoint
Http
POST /orders/{order_id}/send-for-approval
Purpose
Trigger approval workflow
Action
update status
notify n8n
4.9 APPROVE ORDER
Endpoint
Http
POST /orders/{order_id}/approve
Purpose
Confirm order
Action
Plain text
Order_Status = Approved
4.10 REJECT ORDER
Endpoint
Http
POST /orders/{order_id}/reject
Purpose
Reject order
Action
Plain text
Order_Status = Rejected
→ release pigs

4.11 COMPLETE ORDER
Endpoint
Http
POST /orders/{order_id}/complete
Purpose
Mark order as fully collected. Writes pig exit data to PIG_MASTER. This is the terminal success state of an order.
Gate conditions
Order_Status must be "Approved"
All active (non-Cancelled) lines must have a valid Pig_ID
Action
ORDER_LINES (each active line): Line_Status = "Collected", Updated_At = today
PIG_MASTER (each pig): Status = "Sold", On_Farm = "No", Exit_Date = today, Exit_Reason = "Sold", Exit_Order_ID = order_id, Updated_At = today
ORDER_MASTER: Order_Status = "Completed", Updated_At = today
ORDER_STATUS_LOG: full audit entry
Note
This is the first and only action that writes to PIG_MASTER. It is the definitive sale record for each pig.
Output
JSON
{
  "success": true,
  "message": "Order completed successfully.",
  "order_id": "ORD-2026-ABC123",
  "pigs_marked_sold": 3
}

5. READ ENDPOINTS
5.1 Get orders
Http
GET /orders
5.2 Get order detail
Http
GET /orders/{order_id}
5.3 Get available pigs
Http
GET /orders/available-pigs
Source
Plain text
SALES_AVAILABILITY
6. DATA FLOW BETWEEN SYSTEMS
n8n → Backend
n8n sends:
Plain text
intent decisions
order_state
requested_items
Backend → Google Sheets
Backend writes to:
Plain text
ORDER_MASTER
ORDER_LINES
ORDER_STATUS_LOG
PIG_MASTER
Backend → n8n
Returns:
JSON
{
  success,
  message,
  data
}
7. CRITICAL SAFETY RULES
7.1 No direct sheet writes
❌ n8n must NEVER:
update ORDER_MASTER
update ORDER_LINES
update PIG_MASTER
7.2 Reservation control
ONLY backend may:
Plain text
set Reserved_Status
set Reserved_For_Order_ID
7.3 Order ID control
ONLY backend generates:
Plain text
ORD-YYYY-XXXXXX
7.4 Line integrity
Lines must always:
Plain text
match requested_items exactly
8. FAILURE MODES
8.1 Duplicate orders
Cause:
Plain text
n8n calling create twice
8.2 Missing pigs
Cause:
Plain text
reservation endpoint not called
8.3 Wrong pigs assigned
Cause:
Plain text
incorrect matching logic
8.4 Data mismatch
Cause:
Plain text
n8n writing directly to sheets
9. DEBUG CHECKLIST
When something breaks:
Check endpoint called
Check request payload
Check backend response
Check sheet result
Check reservation state
Check order_state vs database
10. FINAL RULE
👉 Backend must ALWAYS be able to answer:
Plain text
What is the real state of the order and pigs?
If not:
👉 System is broken
Where you are now
