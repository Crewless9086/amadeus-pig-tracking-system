# 2.4.5 - Document Send Callback Handler

## Role

Dedicated document-send callback worker for Oom Sakkie quote-send buttons.

Workflow ID: `8b14lAqmyrD0LYZz`  
Status: active in n8n; called by `2 - The GateKeeper` for quote-send/cancel callbacks  
Created for docs: 2026-05-18

## Why This Is Separate

This workflow owns the document-send button result path, but it does not create its own Telegram `callback_query` trigger.

Reason:

- Only one workflow should own normal Telegram callback updates for the Oom Sakkie bot.
- Approval and document button callbacks are now received and authorized by `2 - The GateKeeper`.
- Running two active `callback_query` triggers on the same bot can create the same routing conflict we saw with normal Telegram messages.

Live routing:

1. `2 - The GateKeeper` receives Telegram `message` and `callback_query` updates.
2. GateKeeper authorizes the Telegram user against `ASSISTANT_USERS`.
3. GateKeeper routes approval callbacks to `2.4`.
4. GateKeeper routes quote-send/cancel callbacks to this workflow.

Retired path:

- `2.4.2 - Orders Approval Callback Handler` is historical only and must not be reactivated.

## Callback Data

Supported callback patterns:

```text
quote_send|ORD-2026-XXXXXX|DOC-...|1774
quote_cancel|ORD-2026-XXXXXX|DOC-...
```

## Backend Endpoint Used

```text
POST /api/orders/<order_id>/quote/send-latest-confirmed
```

This endpoint re-checks the selected document at click time before sending.

## Safety Rules

- This workflow must not send directly to Chatwoot.
- This workflow must not call `1.5 - Outbound Document Delivery` directly.
- This workflow must call the backend confirmed-send endpoint only.
- If callback data is missing, stale, or invalid, no document is sent.
- Invoice sending remains out of scope.

## Main Nodes

- `When Executed by Another Workflow`
- `Code - Normalize Document Send Callback`
- `Switch - Route Document Send Callback`
- `Answer Callback - Processing`
- `HTTP - Send Latest Quote Confirmed`
- `Code - Format Send Result`
- `Code - Format Cancel Result`
- `Code - Format Invalid Callback`
- `Telegram - Send Quote Result`
- `Telegram - Send Cancel Result`
- `Telegram - Send Invalid Result`
