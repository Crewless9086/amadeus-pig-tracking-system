# 2.4.5 - Document Send Callback Handler

## Role

Dedicated document-send callback worker for Oom Sakkie quote-send buttons.

Workflow ID: `8b14lAqmyrD0LYZz`  
Status: created in n8n but inactive; local callback router wiring pending backend deploy/import  
Created for docs: 2026-05-18

## Why This Is Separate

This workflow owns the document-send button result path, but it does not create its own Telegram `callback_query` trigger.

Reason:

- Only one workflow should own normal Telegram callback updates for the Oom Sakkie bot.
- Approval button callbacks are already handled by `2.4.2 - Orders Approval Callback Handler`.
- Running two active `callback_query` triggers on the same bot can create the same routing conflict we saw with normal Telegram messages.

Recommended final routing:

1. `2.4.2` remains the Telegram `callback_query` entry point.
2. `2.4.2` routes approval callbacks to `2.4`.
3. `2.4.2` routes quote-send callbacks to this workflow.

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
