# 2.4 - Amadeus Orders Sub Agent

## Role

Oom Sakkie orders sub-agent and order approval workflow.

Workflow ID: `T8LLCAtYDLNRPoRx`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by another workflow.
- Handles order approval request actions.
- Looks up an order through the backend.
- Builds a Telegram approval message.
- Handles Telegram approval chat commands/callbacks.
- Validates that an order is still pending approval before approving or rejecting.
- Calls backend approve/reject endpoints.
- Sends Telegram confirmations or failure messages.

## Backend Endpoints Used

- `GET /api/orders/<order_id>`
- `POST /api/orders/<order_id>/approve`
- `POST /api/orders/<order_id>/reject`

## Main Nodes

- `When Executed by Another Workflow`
- `Switch - Route Approval Request Action`
- `HTTP - View Order`
- `Code - Build Approval Message`
- `Send a text message`
- `Telegram Trigger - Approval Chat`
- `Code - Normalize Telegram Approval Update`
- `Code - Parse Approval Command`
- `IF - Valid Approval Command`
- `HTTP - View Order Before Decision`
- `IF - Order Still Pending Approval`
- `Switch - Approve or Reject`
- `HTTP - Approve Order`
- `HTTP - Reject Order`
- `TELEGRAM - Send Confirmation`

## Planning Notes For Phase 7.3

- This workflow already owns an important part of internal order operations.
- Phase 7.3 should build around this existing workflow, not replace it.
- Current order functions are approval-focused. The new lookup plan should add read-only order/document lookup without weakening the approval safeguards.
- Do not mix customer-facing Sam sales behavior with Oom Sakkie internal approval behavior.

## Phase 7.3 Order Lookup Decision

Owner decision after safety review:

- Keep this existing `2.4` workflow focused on approval requests and approval callbacks.
- Build Oom Sakkie read-only order lookup in a separate workflow: `2.4.4 - Order Lookup Tool`.
- This reduces risk because adding lookup does not require editing/importing the live approval workflow.

The new `2.4.4` workflow should own:

- `find_order`
- `get_order_summary`
- `get_order_documents`

Backend status:

- `GET /api/orders/search` deployed and smoke-tested.
- `GET /api/orders/<order_id>/operator-summary` deployed and smoke-tested.

Planned branch map:

| Action | Backend endpoint | Notes |
| --- | --- | --- |
| `find_order` | `GET /api/orders/search` | Search by order ID, customer name, phone, or conversation ID. |
| `get_order_summary` | `GET /api/orders/<order_id>/operator-summary` | Return compact internal order summary. |
| `get_order_documents` | `GET /api/orders/<order_id>/operator-summary` | Return the `document_summary` section only. |

Protected approval behavior:

- Do not change this workflow while adding read-only lookup.
- Do not route lookup requests through `Telegram Trigger - Approval Chat`.
- Do not let lookup actions approve, reject, cancel, reserve, release, complete, generate, or send anything.

## Telegram Trigger Note

2026-05-18:

- `Telegram Trigger - Approval Chat` was disabled.
- Reason: it was listening for normal `message` updates on the same Oom Sakkie bot as `2 - The GateKeeper`, so general Oom Sakkie messages were being captured by this approval workflow and then dropped when they were not `approve ...` or `reject ...` commands.
- Approval button callbacks remain handled by `2.4.2 - Orders Approval Callback Handler`.
- Approval request/send behavior in this workflow remains active through the execute-workflow entry point.
- Do not re-enable the normal-message Telegram trigger here unless the main GateKeeper routing is redesigned.
