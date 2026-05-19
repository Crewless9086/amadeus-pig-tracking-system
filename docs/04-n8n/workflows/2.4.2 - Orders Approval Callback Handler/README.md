# 2.4.2 - Orders Approval Callback Handler

## Role

Retired historical Telegram callback handler for order approval actions.

Workflow ID: `wmsgzHNywC6okTuI`  
Status: retired / inactive; do not reactivate  
Imported for docs: 2026-05-18

## Historical Behavior

- Received Telegram `callback_query` updates.
- Normalized approval callback payloads.
- Called `2.4 - Amadeus Orders Sub Agent`.
- Answered the Telegram callback query.

## Current Live Behavior

- This workflow has no live role.
- `2 - The GateKeeper` owns all Oom Sakkie Telegram `message` and `callback_query` updates.
- GateKeeper authorizes callbacks before routing.
- GateKeeper routes approval callbacks to `2.4 - Amadeus Orders Sub Agent`.
- GateKeeper routes quote-send/cancel callbacks to `2.4.5 - Document Send Callback Handler`.

## Do Not Reactivate

Reactivating this workflow can register a second Telegram callback trigger for the same Oom Sakkie bot. That can overwrite or delete the bot webhook and make GateKeeper stop receiving messages.

Keep this README as historical documentation only. If an old copy appears in n8n, keep it inactive/archived.
