# Order Steward Workflow

## n8n Workflow Name

`1.2 - Amadeus Order Steward`

## Purpose

Order operation workflow called by the sales workflow for specific order tasks. This is the only workflow that actually does edits/updates or actions towards the orders section. This workflow used the data pass on and pick the correct path to tak and executes the command. 

## Export File

Place the current n8n export in `workflow.json` when available.

## Trigger / Called By
When Executed by Another Workflow
Input data mode: Accept all data

## Inputs
Fields it expects.

## Outputs
[
  {
    "action": "sync_order_lines_from_request",
    "order_id": "ORD-2026-D094F3",
    "changed_by": "Sam",
    "requested_items": [
      {
        "request_item_key": "primary_1",
        "category": "Weaner",
        "weight_range": "10_to_14_Kg",
        "sex": "Any",
        "quantity": 2,
        "intent_type": "primary",
        "status": "active"
      },
      {
        "request_item_key": "addon_1",
        "category": "Finisher",
        "weight_range": "75_to_79_Kg",
        "sex": "Any",
        "quantity": 1,
        "intent_type": "addon",
        "status": "active"
      }
    ]
  }
]

## Main Flow
1. When Executed by Another Workflow

2. Code - Normalize Order Payload
const input = $json;

function clean(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function normalizeRequestedItems(value) {
  if (Array.isArray(value)) {
    return value.map((item) => ({
      request_item_key: clean(item?.request_item_key),
      category: clean(item?.category),
      weight_range: clean(item?.weight_range),
      sex: clean(item?.sex),
      quantity: clean(item?.quantity),
      intent_type: clean(item?.intent_type),
      status: clean(item?.status),
      notes: clean(item?.notes),
    }));
  }
  return [];
}

return [
  {
    json: {
      action: clean(input.action),
      order_id: clean(input.order_id),
      customer_name: clean(input.customer_name),
      customer_phone: clean(input.customer_phone),
      customer_channel: clean(input.customer_channel),
      customer_language: clean(input.customer_language),
      order_source: clean(input.order_source),
      requested_category: clean(input.requested_category),
      requested_weight_range: clean(input.requested_weight_range),
      requested_sex: clean(input.requested_sex),
      requested_quantity: clean(input.requested_quantity),
      quoted_total: clean(input.quoted_total),
      pig_id: clean(input.pig_id),
      unit_price: clean(input.unit_price),
      collection_location: clean(input.collection_location),
      notes: clean(input.notes),
      reason: clean(input.reason),
      changed_by: clean(input.changed_by) || "Order Steward",
      conversation_id: clean(input.conversation_id),
      contact_id: clean(input.contact_id),
      requested_items: normalizeRequestedItems(input.requested_items),
    }
  }
];

3. Switch - Route by Action
Mode: Rule
{{ $json.action }} is equal to create_order
{{ $json.action }} is equal to add_order_line
{{ $json.action }} is equal to view_order
{{ $json.action }} is equal to reserve_order
{{ $json.action }} is equal to release_order
{{ $json.action }} is equal to send_for_approval
{{ $json.action }} is equal to approve_order
{{ $json.action }} is equal to reject_order
{{ $json.action }} is equal to cancel_order
{{ $json.action }} is equal to update_order
{{ $json.action }} is equal to sync_order_lines_from_request

3.1 - Create Order
3.1.1 Set - Build Create Order Body
Mode: Manual Mapping
Fields to Set:
order_date = string = {{$now.toFormat('yyyy-MM-dd')}}
customer_name = string = {{ $('Code - Normalize Order Payload').item.json.customer_name }}
customer_phone = string = {{ $('Code - Normalize Order Payload').item.json.customer_phone }}
customer_channel = string = {{ $('Code - Normalize Order Payload').item.json.customer_channel }}
customer_language = string = {{ $('Code - Normalize Order Payload').item.json.customer_language }}
order_source = string = {{ $('Code - Normalize Order Payload').item.json.order_source }}
requested_category = string = {{ $('Code - Normalize Order Payload').item.json.requested_category }}
requested_weight_range = string = {{ $('Code - Normalize Order Payload').item.json.requested_weight_range }}
requested_sex = string = {{ $('Code - Normalize Order Payload').item.json.requested_sex }}
requested_quantity = string = {{ $('Code - Normalize Order Payload').item.json.requested_quantity }}
quoted_total = string = {{ $('Code - Normalize Order Payload').item.json.quoted_total }}
notes = string = {{ $('Code - Normalize Order Payload').item.json.notes }}
created_by = string = {{ $('Code - Normalize Order Payload').item.json.changed_by }}

3.1.2 HTTP - Create Order
Method: POST
URL: https://amadeus-pig-tracking-system.onrender.com/api/master/orders
Send Body: JSON
Specify Body: Using JSON
JSON: {{$json}}
Response Format: JSON

3.1.3 Set - Format Create Order Result
Mode
Manual Mapping
Fields to Set
success

String
=
{{$json.success}}
 
action

String
create_order
order_id

String
=
{{$json.order_id}}
 
message

String
=
{{$json.message}}
 
status

String
Draft
customer_name

String
=
{{$node["Code - Normalize Order Payload"].json["customer_name"]}}
 
requested_category

String
=
{{$node["Code - Normalize Order Payload"].json["requested_category"]}}
 
requested_weight_range

String
=
{{ $('Code - Normalize Order Payload').item.json.requested_weight_range }}
 


3.2 - Add Order Line
3.2.1 Set - Build Add Order Line Body
Mode
Manual Mapping
Fields to Set
order_id

String
=
{{ $json.order_id }}
 
pig_id

String
=
{{ $json.pig_id }}
 
unit_price

String
=
{{$json.unit_price}}
 
notes

String
=
{{$json.notes}}

3.2.2 HTTP - Add Order Line
Method
POST
URL
https://amadeus-pig-tracking-system.onrender.com/api/master/order-lines
Authentication
None

Send Query Parameters: FALSE

Send Headers: FALSE

Send Body
Body Content Type
JSON
Specify Body
Using JSON
JSON
{{$json}}

Response Format: JSON


3.2.3 Set - Format Add ORder Line Result
Mode
Manual Mapping
Fields to Set
success

String
=
{{$json.success}}
 
action

String
add_order_line
order_id

String
=
{{$node["Code - Normalize Order Payload"].json["order_id"]}}
 
pig_id

String
=
{{$node["Code - Normalize Order Payload"].json["pig_id"]}}
 
message

String
=
{{$json.message}}
 
unit_price

String
=
{{$node["Code - Normalize Order Payload"].json["unit_price"]}}
 
notes

String
=
{{ $('Code - Normalize Order Payload').item.json.notes }}
 

3.3 - View Order
3.3.1 HTTP - View Order
Method
GET
URL
https://amadeus-pig-tracking-system.onrender.com/api/orders/{{$json.order_id}}
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: FALSE

Send Body: FALSE
Response Format: JSON


3.3.2 Set - Format View Order Result
Mode
Manual Mapping
Fields to Set
success

Boolean
=
{{ $json.success }}
 
action

String
view_order
order_id

String
=
{{$json.order.order_id}}
 
message

String
Order retrieved successfully.
order_status

String
=
{{$json.order.order_status}}
 
approval_status

String
=
{{$json.order.approval_status}}
 
customer_name

String
=
{{$json.order.customer_name}}
 
customer_channel

String
=
{{$json.order.customer_channel}}
 
requested_category

String
=
{{$json.order.requested_category}}
 
requested_weight_range

String
=
{{$json.order.requested_weight_range}}
 
requested_quantity

String
=
{{$json.order.requested_quantity}}
 
reserved_pig_count

String
=
{{$json.order.reserved_pig_count}}
 
line_count

String
=
{{$json.order.line_count}}
 
final_total

String
=
{{$json.order.final_total}}
 
lines

String
=
{{$json.lines}}

3.4 - Reserve Order
3.4.1 HTTP - Reserve Order
Method
POST
URL
https://amadeus-pig-tracking-system.onrender.com/api/orders/{{$json.order_id}}/reserve
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: FALSE

Send Body: TRUE
Body Content Type: JSON
Specify Body
Using JSON
JSON:
1 {}

Response Format: JSON


3.4.2 Set - Format Reserve Result
Mode
Manual Mapping
Fields to Set
success

String
=
{{$json.success}}
 
action

String
reserve_order
order_id

String
=
{{$json.order_id}}
 
message

String
=
{{$json.message}}
 
reserved_pig_count

String
=
{{$json.reserved_pig_count}}
 
changed_count

String
=
{{$json.changed_count}}

3.5 - Release Order
3.5.1 HTTP - Release Order
Method
POST
URL
https://amadeus-pig-tracking-system.onrender.com/api/orders/{{$json.order_id}}/release
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: FALSE

Send Body: TRUE
Body Content Type
JSON
Specify Body
Using JSON
JSON
1 {}

Response Format: JSON

3.5.2 Set - Format Release Result
Mode
Manual Mapping
Fields to Set
success

Boolean
=
{{ $json.success }}
 
action

String
release_order
order_id

String
=
{{$json.order_id}}
 
message

String
=
{{$json.message}}
 
reserved_pig_count

String
=
{{$json.reserved_pig_count}}
 
changed_count

String
=
{{$json.changed_count}}
 
3.6 - Send for Approval
3.6.1 Set - Build Send for Approval Body
Mode
Manual Mapping
Fields to Set
changed_by

String
=
{{ $json.changed_by }}
 

3.6.2 HTTP - Send for Approval
Method
POST
URL
https://amadeus-pig-tracking-system.onrender.com/api/orders/{{$node["Code - Normalize Order Payload"].json["order_id"]}}/send-for-approval
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: FALSE

Send Body: TRUE
Body Content Type
JSON
Specify Body
Using JSON
JSON
{{$json}}
 
Response Format: JSON

3.6.3 Set - Format Send for Approval Result
Mode
Manual Mapping
Fields to Set
success

String
=
{{$json.success}}
 
action

String
send_for_approval
order_id

String
=
{{$json.order_id}}
 
message

String
=
{{$json.message}}
 
order_status

String
Pending_Approval
approval_status

String
Pending
changed_by

String
=
{{$node["Code - Normalize Order Payload"].json["changed_by"]}}
 

3.7 - Approve Order
3.7.1 Set - Build Approve Body
Mode
Manual Mapping
Fields to Set
changed_by

String
=
{{ $json.changed_by }}

3.7.2 HTTP - Approve Order
Method
POST
URL
https://amadeus-pig-tracking-system.onrender.com/api/orders/{{$node["Code - Normalize Order Payload"].json["order_id"]}}/approve
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: FALSE

Send Body: TRUE
Body Content Type
JSON
Specify Body
Using JSON
JSON
{{$json}}
 
Response Format: JSON


3.7.3 Set - Format Approve Result
Mode
Manual Mapping
Fields to Set
success

String
=
{{$json.success}}
 
action

String
approve_order
order_id

String
=
{{$json.order_id}}
 
message

String
=
{{$json.message}}
 
order_status

String
Approved
approval_status

String
Approved
changed_by

String
=
{{$node["Code - Normalize Order Payload"].json["changed_by"]}}
 

3.8 - Reject Order
3.8.1 Set - Build Reject Body
Mode
Manual Mapping
Fields to Set
changed_by

String
=
{{$json.changed_by}}

3.8.2 HTTP - Reject Order
Method
POST
URL
https://amadeus-pig-tracking-system.onrender.com/api/orders/{{$node["Code - Normalize Order Payload"].json["order_id"]}}/reject
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: FALSE

Send Body: TRUE
Body Content Type
JSON
Specify Body
Using JSON
JSON
{{$json}}
 
Response Format: JSON


3.8.3 Set - Format Reject Result
Mode
Manual Mapping
Fields to Set
success

String
=
{{$json.success}}
 
action

String
reject_order
order_id

String
=
{{ $json.order_id }}
 
message

String
=
{{ $json.message }}
 
order_status

String
Cancelled
approval_status

String
Rejected
changed_by

String
=
{{ $('Code - Normalize Order Payload').item.json.changed_by }}


3.11 - Cancel Order

Purpose: customer-requested cancellation through the backend only.

Input fields expected from `1.0`:

- `action = cancel_order`
- `order_id`
- `changed_by = Sam`
- `reason` optional customer reason, passed as an empty string when absent

3.11.1 Set - Build Cancel Body
Mode: Manual Mapping
Fields to Set:
changed_by = {{ $json.changed_by }}
reason = {{ $json.reason }}

3.11.2 HTTP - Cancel Order
Method: POST
URL:
https://amadeus-pig-tracking-system.onrender.com/api/orders/{{$node["Code - Normalize Order Payload"].json["order_id"]}}/cancel
Body: {{$json}}
Response Format: JSON

3.11.3 Set - Format Cancel Result
Fields to Set:
success = {{$json.success}}
action = cancel_order
order_id = {{ $json.order_id }}
message = {{ $json.message }}
order_status = Cancelled
approval_status = Not_Required
payment_status = Cancelled
changed_by = {{ $('Code - Normalize Order Payload').item.json.changed_by }}
cancelled_line_count = {{ $json.cancelled_line_count }}

Rule: this branch must not directly edit Google Sheets. The backend owns cancelling linked lines, releasing reservations, resetting `Reserved_Pig_Count`, and writing `ORDER_STATUS_LOG`.

3.9 - Update Order
3.9.1 Code - Build Update ORder Payload
const item = $json || {};

const body = {};

const orderId = String(item.order_id || "").trim();
const changedBy = String(item.changed_by || "").trim() || "Sam";

if (!orderId) {
  throw new Error("order_id is required for update_order.");
}

if (item.requested_quantity !== undefined && item.requested_quantity !== null && String(item.requested_quantity).trim() !== "") {
  body.requested_quantity = item.requested_quantity;
}

if (item.requested_category !== undefined && item.requested_category !== null && String(item.requested_category).trim() !== "") {
  body.requested_category = String(item.requested_category).trim();
}

if (item.requested_weight_range !== undefined && item.requested_weight_range !== null && String(item.requested_weight_range).trim() !== "") {
  body.requested_weight_range = String(item.requested_weight_range).trim();
}

if (item.requested_sex !== undefined && item.requested_sex !== null && String(item.requested_sex).trim() !== "") {
  body.requested_sex = String(item.requested_sex).trim();
}

if (item.collection_location !== undefined && item.collection_location !== null && String(item.collection_location).trim() !== "") {
  body.collection_location = String(item.collection_location).trim();
}

if (item.notes !== undefined && item.notes !== null && String(item.notes).trim() !== "") {
  body.notes = String(item.notes).trim();
}

body.changed_by = changedBy;

const updatableFieldCount =
  (body.requested_quantity !== undefined ? 1 : 0) +
  (body.requested_category !== undefined ? 1 : 0) +
  (body.requested_weight_range !== undefined ? 1 : 0) +
  (body.requested_sex !== undefined ? 1 : 0) +
  (body.collection_location !== undefined ? 1 : 0) +
  (body.notes !== undefined ? 1 : 0);

if (updatableFieldCount === 0) {
  throw new Error("No non-empty order fields were provided for update_order.");
}

return [
  {
    json: {
      ...item,
      order_id: orderId,
      patch_body: body
    }
  }
];

3.9.2 HTTP - Update Order
Method
PATCH
URL
https://amadeus-pig-tracking-system.onrender.com/api/master/orders/{{ $json.order_id }}
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: TRUE
Specify Headers
Using Fields Below
Headers

Content-Type
Name
Content-Type
Value
application/json

Send Body: TRUE
Body Content Type
JSON
Specify Body
Using JSON
JSON
{{ $json.patch_body }}

3.9.3 Code - Format Update Order Result
const item = $json || {};

return [
  {
    json: {
      success: item.success === true,
      action: "update_order",
      order_id: item.order_id || "",
      message: item.message || "",
      updated_fields: Array.isArray(item.updated_fields) ? item.updated_fields : [],
      changed_by: item.changed_by || ""
    }
  }
];

Phase 1.3 payment method note:

`update_order` now accepts `payment_method` from `1.0` and forwards it to backend `PATCH /api/master/orders/{order_id}` when the value is `Cash` or `EFT`. Backend maps this API field to `ORDER_MASTER.Payment_Method` and rejects changes once the order is beyond `Draft`.

3.10 - Sync Order Lines
3.10.1 Set - Build Sync Order Lines Payload
Mode
Manual Mapping
Fields to Set
order_id

String
=
{{$json.order_id}}
 
changed_by

String
=
{{$json.changed_by || "Order Steward"}}
 
requested_items

Array
=
{{$json.requested_items}}
 

3.10.2 HTTP - Sync ORder Lines
Method
POST
URL
https://amadeus-pig-tracking-system.onrender.com/api/master/orders/{{$json.order_id}}/sync-lines
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: TRUE
Specify Headers
Using Fields Below
Headers

Content-Type
Name
Content-Type
Value
application/json

Send Body: TRUE
Body Content Type
JSON
Specify Body
Using JSON
JSON
{{ {
  changed_by: $json.changed_by,
  requested_items: $json.requested_items
} }}
 
Response Format: JSON

3.10.3 Set - Format Sync Order Lines Result
Mode
Manual Mapping
Fields to Set
sync_success

Boolean
=
{{$json.success}}
 
sync_action

String
=
{{$json.action}}
 
sync_order_id

String
=
{{$json.order_id}}
 
sync_results

Array
=
{{$json.results}}
 

3.11 - Create Order With Lines

Purpose:

Create a draft order and immediately sync requested `ORDER_LINES` in one `1.2` execution. This is used by `1.0` for first-turn committed customer requests where `requested_items[]` is already populated.

Action:

`create_order_with_lines`

Route:

`Switch - Route by Action` output `Create Order With Lines`.

Branch chain:

`Set - Build Create With Lines Body` -> `HTTP - Create With Lines Order` -> `Code - Build Sync After Create Payload` -> `HTTP - Sync New Draft Lines` -> `Code - Format Create With Lines Result`

Important ownership rule:

`1.0` decides whether to call `create_order` or `create_order_with_lines`. `1.2` owns the actual create + sync operation.

`Code - Build Sync After Create Payload` must read `requested_items[]` from `Code - Normalize Order Payload`, not from the create-order HTTP response. At that point `$json` is the backend create response and does not contain the original requested items.

Combined result fields:

- `success`: true only when both create and sync succeeded
- `action`: `create_order_with_lines`
- `order_id`: created order ID
- `order_status`: `Draft`
- `sync_success`: backend sync-lines success
- `sync_results`: created/matched line details
- `sync_message`: sync-lines message for diagnostics

Live verification:

2026-04-29: `ORD-2026-879091` created from a first-turn WhatsApp request for 3 Weaners in `7_to_9_Kg`. `ORDER_LINES` received three Draft / Not_Reserved rows with `request_item_key = primary_1`.

## Important Rules
This workflow is responsible for all action to be taken with related to orders only this workflow access and make changes not the others.

## Known Issues / Questions
1. Split requested item sync still needs hardening for multi-key requests such as male/female splits.
2. View Order should become available for Sam through a safe `1.2`/backend review action so replies can use backend-confirmed order truth.