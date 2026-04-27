# API Structure

## Purpose

Documents the current Flask order API used by the web app and n8n workflows.

All order API routes are registered under `/api`.

## Route Summary

| Method | Path | Current purpose | Main caller |
| --- | --- | --- | --- |
| `GET` | `/api/orders` | List orders from `ORDER_OVERVIEW`. | Web app, future review tooling. |
| `GET` | `/api/orders/<order_id>` | Return one order with matching `ORDER_LINES`. | Web app, future Order Steward review. |
| `GET` | `/api/orders/available-pigs` | Return sale-available pigs from `SALES_AVAILABILITY`. | Web app/order tooling. |
| `POST` | `/api/orders/<order_id>/reserve` | Mark order lines as reserved and update master reserved count. | Web app, future steward action. |
| `POST` | `/api/orders/<order_id>/release` | Release reserved order lines and reset master reserved count. | Web app, future cancel/reject flow. |
| `POST` | `/api/orders/<order_id>/send-for-approval` | Mark order pending approval and notify approval workflow. | Web app. |
| `POST` | `/api/orders/<order_id>/approve` | Approve order. | Web app/human action. |
| `POST` | `/api/orders/<order_id>/reject` | Reject approval and mark order cancelled. | Web app/human action. |
| `POST` | `/api/orders/<order_id>/cancel` | Customer-cancel order, cancel linked lines, and release reservations. | Web app, future Order Steward action. |
| `POST` | `/api/orders/<order_id>/complete` | Complete order, collect lines, and update sold/exited pigs. | Web app/human action. |
| `POST` | `/api/master/orders` | Create draft order. | `1.2 - Amadeus Order Steward`, web app. |
| `PATCH` | `/api/master/orders/<order_id>` | Update allowed draft/header fields. | `1.2 - Amadeus Order Steward`, web app. |
| `POST` | `/api/master/orders/<order_id>/sync-lines` | Sync requested items into order lines. | `1.2 - Amadeus Order Steward`. |
| `POST` | `/api/master/order-lines` | Create one order line. | Web app/manual tooling. |
| `PATCH` | `/api/master/order-lines/<order_line_id>` | Update unit price and notes. | Web app/manual tooling. |
| `DELETE` | `/api/master/order-lines/<order_line_id>` | Soft-cancel one line. | Web app/manual tooling. |

## Current `1.2 - Order Steward` Live Actions

The n8n docs currently treat only these actions as live from Sam/`1.0`:

| Steward action | Backend endpoint |
| --- | --- |
| `create_order` | `POST /api/master/orders` |
| `update_order` | `PATCH /api/master/orders/<order_id>` |
| `sync_order_lines_from_request` | `POST /api/master/orders/<order_id>/sync-lines` |

Other backend endpoints may exist and work from the web app, but they should not be treated as active Sam tools until wired, tested, and documented.

## Important Payload Contracts

### Create Order

Endpoint: `POST /api/master/orders`

Important fields:

- `order_date`
- `customer_name`
- `customer_phone`
- `customer_channel`
- `customer_language`
- `order_source`
- `requested_category`
- `requested_weight_range`
- `requested_sex`
- `requested_quantity`
- `quoted_total`
- `notes`
- `created_by`

Current result includes success state, generated `order_id`, and any warnings.

### Update Order

Endpoint: `PATCH /api/master/orders/<order_id>`

Allowed fields in current validation:

- `requested_quantity`
- `requested_category`
- `requested_weight_range`
- `requested_sex`
- `collection_location`
- `notes`
- `changed_by`

Current validation does not allow arbitrary header updates. Add new fields deliberately.

### Sync Lines

Endpoint: `POST /api/master/orders/<order_id>/sync-lines`

Payload:

```json
{
  "changed_by": "Sam",
  "requested_items": [
    {
      "request_item_key": "primary_1",
      "category": "Young Piglets",
      "weight_range": "2_to_4_Kg",
      "sex": "Male",
      "quantity": 2,
      "intent_type": "primary",
      "status": "active",
      "notes": "Customer requested male piglets"
    }
  ]
}
```

Important rules:

- `request_item_key` is required and must remain stable across repeated syncs.
- Split items such as `primary_1` and `primary_2` must both be preserved.
- Exact-match sync can cancel/recreate lines.
- Partial/no-match behavior needs hardening before Sam treats the order as fully updated.

## Reject And Cancel Behavior

Current reject endpoint behavior:

- sets `ORDER_MASTER.Order_Status = Cancelled`
- sets `ORDER_MASTER.Approval_Status = Rejected`
- cancels linked non-cancelled/non-collected order lines
- sets linked line `Reserved_Status` values to `Not_Reserved`
- resets `ORDER_MASTER.Reserved_Pig_Count` to `0`
- appends `ORDER_STATUS_LOG` when rejection or cleanup changes state
- blocks completed orders from being rejected

Current customer cancel endpoint behavior:

- `POST /api/orders/<order_id>/cancel` sets `Order_Status = Cancelled`.
- It sets `Approval_Status = Not_Required`.
- It sets `Payment_Status = Cancelled`.
- It cancels linked non-cancelled/non-collected order lines.
- It sets linked line `Reserved_Status` values to `Not_Reserved`.
- It resets `ORDER_MASTER.Reserved_Pig_Count` to `0`.
- It writes `ORDER_STATUS_LOG` when cancellation or cleanup changes state.
- It blocks completed orders from being cancelled.
- It does not convert already rejected orders into customer-cancelled orders.

## Order Review Direction

Sam should preferably request order context through `1.2 - Amadeus Order Steward` and backend review endpoints, not by directly reading `ORDER_OVERVIEW` as a production tool.

Reason:

- backend can verify customer/order ownership
- backend can filter the fields Sam receives
- backend can avoid exposing irrelevant orders
- backend responses are easier to test than direct AI sheet access
