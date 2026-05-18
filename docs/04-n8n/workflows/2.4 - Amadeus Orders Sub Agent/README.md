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

## Planned 7.3 Lookup Additions

Owner direction:

- Build Oom Sakkie order lookup into this existing `2.4` workflow because it is the order sub-agent.
- Preserve the current approval request/callback behavior.

Planned read-only actions:

- `find_order`
- `get_order_summary`
- `get_order_documents`

Recommended implementation shape:

- Add lookup actions as separate switch routes.
- Use backend endpoints for all order truth.
- Prefer a backend `GET /api/orders/search` endpoint before adding name/phone search behavior to n8n.
- Do not add document-send behavior until read-only lookup is tested.
- Do not expose these actions through approval callback commands.
