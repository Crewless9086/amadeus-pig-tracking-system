# 2.4.4 - Order Lookup Tool

## Role

Read-only Oom Sakkie order lookup tool.

Workflow ID: `1VNdetSbgP0ffNyH`  
Live status: active for read-only lookup and guarded quote-send preparation  
Created for docs: 2026-05-18

## Why This Is Separate From `2.4`

`2.4 - Amadeus Orders Sub Agent` is already live and handles order approval requests, approval callbacks, and approve/reject actions.

This workflow is separate to reduce risk:

- read-only lookup can be changed/tested without touching the approval workflow
- approval callbacks remain protected
- no lookup action can accidentally approve, reject, cancel, reserve, release, complete, generate, or send a customer document

## What It Does

Runs when called by Oom Sakkie and supports read-only order lookup actions:

- `find_order`
- `get_order_summary`
- `get_order_documents`
- `prepare_latest_quote_send`

`prepare_latest_quote_send` prepares operator confirmation buttons only. It does not send a customer document.

## Backend Endpoints Used

- `GET /api/orders/search`
- `GET /api/orders/<order_id>/operator-summary`
- `POST /api/orders/<order_id>/quote/prepare-send`

## Inputs

| Field | Required | Notes |
| --- | --- | --- |
| `input` | no | Raw Oom Sakkie message. The workflow can infer a safe lookup action and identifiers from this when structured fields are missing. |
| `action` | yes | `find_order`, `get_order_summary`, `get_order_documents`, or `prepare_latest_quote_send`. |
| `order_id` | no | Required for summary/documents; optional for search. |
| `customer_phone` | no | Search input. |
| `customer_name` | no | Search input. |
| `conversation_id` | no | Search input. |
| `telegram_chat_id` | no | Required for quote-send button preparation. Passed from `2.0`. |
| `telegram_user_id` | no | Trace field for quote-send button preparation. |
| `telegram_user_name` | no | Trace/display field for quote-send button preparation. |
| `status_scope` | no | `active`, `history`, or `all`; defaults to `active`. |
| `limit` | no | Defaults to `5`; backend caps at `10`. |
| `changed_by` | no | Trace only. No write actions in this workflow. |

Structured fields are preferred, but the first Oom Sakkie integration may pass only `input`. In that case the normalize node tries to infer:

- `order_id` from `ORD-YYYY-XXXXXX` style references
- `customer_phone` from phone-like digit strings
- `conversation_id` from phrases like `conversation 1774`
- `customer_name` from simple name/order search wording
- `action` from the requested intent, defaulting to `find_order` unless an exact order ID implies summary or document lookup

## Main Nodes

- `When Executed by Another Workflow`
- `Code - Normalize Lookup Payload`
- `Switch - Route Lookup Action`
- `HTTP - Search Orders`
- `Code - Format Find Order Result`
- `HTTP - Get Operator Summary`
- `Code - Format Order Summary Result`
- `HTTP - Get Documents Summary`
- `Code - Format Documents Result`
- `HTTP - Prepare Latest Quote Send`
- `Code - Format Prepare Quote Send Result`
- `Telegram - Send Quote Confirmation Buttons`
- `Code - Format Prepare Quote Tool Response`
- `Set - Invalid Lookup Action`

The trigger declares the accepted workflow inputs so n8n can activate the workflow:

- `input`
- `action`
- `order_id`
- `customer_phone`
- `customer_name`
- `conversation_id`
- `telegram_chat_id`
- `telegram_user_id`
- `telegram_user_name`
- `status_scope`
- `limit`
- `changed_by`

## Safety Rules

- Lookup actions are read-only.
- Do not add approval, rejection, cancellation, reservation, release, completion, generation, or document-send actions.
- Do not return Google Drive URLs.
- This workflow may send an operator-only Telegram confirmation button message.
- After sending that direct Telegram button message, it returns `__NO_TELEGRAM_REPLY__` so `2.0` can suppress the duplicate acknowledgement.
- It must not send customer documents.
- Customer document sending remains owned by backend confirmed-send endpoints and the separate callback worker.

## Planned Caller

`2.0 - OOM SAKKIE - Amadeus Assistant Agent` should call this workflow through a new tool named `Orders_Info_Tool`.
