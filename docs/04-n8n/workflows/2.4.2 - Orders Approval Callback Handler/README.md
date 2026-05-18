# 2.4.2 - Orders Approval Callback Handler

## Role

Telegram callback handler for order approval actions.

Workflow ID: `wmsgzHNywC6okTuI`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Receives Telegram callback updates.
- Normalizes the callback payload.
- Calls `2.4 - Amadeus Orders Sub Agent`.
- Answers the Telegram callback query.

## Main Nodes

- `Telegram Trigger`
- `Code - Normalize Callback`
- `Call '2.4A - Amadeus Orders Sub Agent'`
- `Answer Query a callback`

## Calls

- Calls workflow `2.4 - Amadeus Orders Sub Agent` (`T8LLCAtYDLNRPoRx`).

## Planning Notes

- This is part of the existing order approval path.
- Phase 7.3 lookup work should not break callback approval handling.
- The old `2.4A` cached workflow name should be cleaned up only after a deliberate workflow maintenance pass.
