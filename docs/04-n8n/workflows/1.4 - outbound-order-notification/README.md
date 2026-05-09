# 1.4 - Outbound Order Notification

## Role

Backend-triggered customer notification workflow for order approval and rejection outcomes.

This workflow is intentionally separate from `1.0 - SAM - Sales Agent - Chatwoot`. The inbound sales agent should not invent or independently send approval/rejection outcomes. The backend sends this workflow only after the order state transition has succeeded.

## Trigger

Webhook called by Flask through `ORDER_NOTIFICATION_WEBHOOK_URL`.

Expected payload:

```json
{
  "event_type": "order_approved",
  "order_id": "ORD-2026-XXXXXX",
  "conversation_id": "12345",
  "customer_name": "Customer Name",
  "customer_phone": "+27000000000",
  "customer_channel": "WhatsApp",
  "order_status": "Approved",
  "approval_status": "Approved",
  "changed_by": "App",
  "message_text": "Your order has been approved. We have reserved the pigs linked to your order and will keep you posted on the next step.",
  "trigger_source": "Flask App",
  "extra": {}
}
```

Allowed `event_type` values:

- `order_approved`
- `order_rejected`

## Message Texts

Approval:

`Your order has been approved. We have reserved the pigs linked to your order and will keep you posted on the next step.`

Rejection:

`Your order was reviewed, but we cannot approve it at this stage. We will follow up if there is another suitable option.`

The workflow must send the backend-provided `message_text` exactly. Do not ask an AI node to rewrite these messages.

## Chatwoot Lookup

Use `conversation_id` from the webhook payload. Backend stores this as `ORDER_MASTER.ConversationId` when the draft order is created from `1.0` to `1.2`.

If `conversation_id` is blank, the workflow must not send a customer message. Return a clear error so backend can log a manual follow-up warning.

## Workflow Shape

1. Webhook receives backend event.
2. Code node validates required fields and event type.
3. IF node blocks invalid payloads.
4. HTTP Request node posts `message_type = outgoing`, `private = false`, and `content = message_text` to the Chatwoot conversation messages endpoint.
5. Respond node returns success/error details.

## Backend Contract

Backend treats this workflow as non-blocking. If the webhook fails, the order transition remains committed and backend writes a warning to `ORDER_STATUS_LOG`.
