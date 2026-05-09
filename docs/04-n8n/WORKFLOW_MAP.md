# Workflow Map

## Purpose

Maps the complete n8n workflow suite and the role of each workflow.

## Suite Overview

```mermaid
flowchart TD
  incoming["Incoming Chatwoot Message"] --> wf10["1.0 Sales Agent Chatwoot"]
  wf10 --> classify["Classify: AUTO, CLARIFY, ESCALATE"]
  classify --> autoPath[AUTO]
  classify --> clarifyPath[CLARIFY]
  classify --> escalatePath[ESCALATE]
  autoPath --> orderState["Build Order State"]
  orderState --> wf12["1.2 Order Steward"]
  wf12 --> backend["Backend API"]
  backend --> sheets["Google Sheets"]
  clarifyPath --> salesAgent["AI Sales Agent Reply"]
  salesAgent --> chatwootReply["Chatwoot Reply"]
  escalatePath --> handoffSheet["Escalation Sheet"]
  escalatePath --> telegramAlert["Telegram Alert"]
  telegramAlert --> wf11["1.1 Telegram Human Reply"]
  wf11 --> chatwootReply
  wf10 -. disabled .-> wf13["1.3 Media Tool"]
  backend --> wf14["1.4 Outbound Order Notification"]
  wf14 --> chatwootReply
```

## `1.0 - SAM - Sales Agent - Chatwoot`

Role: customer-facing sales hub.

Trigger: Chatwoot inbound webhook.

Primary responsibilities:

- accept incoming customer text or audio messages
- block non-customer/loop messages
- normalize Chatwoot IDs and message fields
- transcribe voice notes when present
- fetch and format conversation history
- classify the message into `AUTO`, `CLARIFY`, or `ESCALATE`
- run Sam as the sales agent with sales stock and farm-info tools
- build structured order state from the conversation
- call `1.2 - Amadeus Order Steward` for currently supported order actions
- write escalation records and notify Telegram when human help is needed
- send final replies back to Chatwoot
- manage customer-cancel confirmation state through Chatwoot `pending_action`

Current live order routes called from `1.0`:

- `create_order`
- `create_order_with_lines`
- `update_order`
- `sync_order_lines_from_request`
- `get_order_context` (read-only prefetch when a draft id exists, before AUTO `Code - Build Order State`)
- `cancel_order`
- `send_for_approval`

Current disabled capability:

- `Send_Pictures` tool workflow, which should point to `1.3 - SAM - Sales Agent - Media Tool` when ready.

## `1.1 - SAM - Sales Agent - Escalation Telegram`

Role: async human reply workflow.

Trigger: Telegram message from the approved human chat.

Primary responsibilities:

- parse the human Telegram reply and ticket ID
- retrieve escalation ticket detail from the handoff sheet
- polish the human reply without changing meaning
- send the answer to the correct Chatwoot conversation
- update the escalation sheet status
- return the Chatwoot conversation to `conversation_mode = AUTO`
- delete Telegram messages after reply when implemented

Relationship to `1.0`: coordinated through Telegram and the escalation sheet, not through direct `Execute Workflow` calls.

## `1.2 - Amadeus Order Steward`

Role: order action worker.

Trigger: executed by another workflow, mainly `1.0`.

Primary responsibilities for current `1.0` use:

- normalize incoming action payloads
- route by `action`
- call backend API endpoints
- return structured success/error responses to `1.0`

Currently documented as live for `1.0` only:

- `create_order`
- `create_order_with_lines`
- `update_order`
- `sync_order_lines_from_request`
- `get_order_context`
- `cancel_order`
- `send_for_approval`

Other actions present in the workflow should be treated as steward capability or test/planned paths until `1.0` actively calls them.

Customer cancel routing uses `CANCEL_PENDING`, `CANCEL_ORDER`, and `CLEAR_PENDING` inside `1.0`, with the actual cancellation executed through `1.2` and the backend.

First-turn committed orders with non-empty `requested_items[]` use `create_order_with_lines`. `1.0` chooses the action, while `1.2` creates the draft, syncs `ORDER_LINES`, and returns one combined success result.

Order context today: `get_order_context` in `1.2` calls `GET /api/orders/<id>` and returns slim header + line metadata to `1.0` for merge in `Code - Build Order State`.

Preferred direction for richer review UIs: keep using `1.2` and backend endpoints rather than giving Sam direct `ORDER_OVERVIEW` sheet tools.

## `1.3 - SAM - Sales Agent - Media Tool`

Role: image/media sender.

Trigger: executed as a tool workflow when enabled.

Current status: disabled until fixed and tested.

Primary responsibilities when enabled:

- receive `account_id`, `conversation_id`, `inbox_id`, `category_key`, `send_mode`, and `count`
- map media category to Google Drive folder
- find eligible images
- send images to Chatwoot
- update `images_sent_offset_map` so repeat requests do not resend the same images unnecessarily

## `1.4 - Outbound Order Notification`

Role: backend-triggered customer notification workflow.

Trigger: webhook called by Flask through `ORDER_NOTIFICATION_WEBHOOK_URL` after a successful approval or rejection.

Primary responsibilities:

- receive `event_type`, `order_id`, `conversation_id`, `message_text`, customer metadata, and extra transition context from backend
- validate that `event_type` is one of `order_approved` or `order_rejected`
- require `conversation_id` before sending to Chatwoot
- send the exact backend-provided `message_text` to the Chatwoot conversation
- return structured success/error details to backend

Relationship to `1.0`: separate outbound workflow. `1.0` remains the inbound sales hub and does not own post-approval/rejection messages.

## Change Rule

Any structural workflow change must update this map and the affected workflow README.
