# 2.4.3 - Order Approval Request Webhook

## Role

Webhook entry point for order approval request notifications.

Workflow ID: `k4XVMoJ1hK09PIvT`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Receives an order approval request webhook.
- Normalizes the webhook payload.
- Validates the request.
- Calls `2.4 - Amadeus Orders Sub Agent`.
- Responds to the webhook with success or invalid-payload response.

## Main Nodes

- `Webhook - Order Approval Request`
- `Code - Normalize Webhook Payload`
- `IF - Valid Approval Request`
- `Call '2.4A - Amadeus Orders Sub Agent'`
- `Respond to Webhook - Success`
- `Respond to Webhook - Invalid Payload`

## Calls

- Calls workflow `2.4 - Amadeus Orders Sub Agent` (`T8LLCAtYDLNRPoRx`).

## Planning Notes

- This workflow is an integration point for backend/order approval notifications.
- It should remain separate from ad hoc Oom Sakkie lookup questions.
- Any future approval changes should be tested end-to-end with `2.4`.
