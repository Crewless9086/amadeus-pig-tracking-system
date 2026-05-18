# 2 - The GateKeeper

## Role

Live Telegram access gate for Oom Sakkie.

Workflow ID: `yt4qc1kP5riAfLfL`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Receives Telegram messages.
- Prepares the inbound message.
- Reads the `ASSISTANT_USERS` sheet from the `Amadeus_Users` spreadsheet.
- Normalizes the authorization check.
- Routes unauthorized users to a Telegram rejection message.
- Routes authorized users to `2.0 - OOM SAKKIE - Amadeus Assistant Agent`.

## Main Nodes

- `Telegram Trigger`
- `Prepare Message`
- `Get User Info`
- `Normalize Auth Check`
- `Security Check`
- `Send Not Authorized`
- `Call '2.0 - OOM SAKKIE - Amadeus Assistant Agent'`

## Calls

- Calls workflow `2.0 - OOM SAKKIE - Amadeus Assistant Agent` (`6UscGE44eTfdLp1A`).

## Planning Notes

- This workflow is the correct entry point for operator access control.
- Oom Sakkie planning should preserve this gate and not expose the main assistant directly.
- Any new Oom Sakkie order lookup capability should remain behind this gate.

## Telegram Routing Note

2026-05-18:

- This workflow owns normal Telegram `message` updates for Oom Sakkie.
- The conflicting normal-message trigger in `2.4 - Amadeus Orders Sub Agent` was disabled because it intercepted general Oom Sakkie messages before they reached this GateKeeper.
- `2.4.2 - Orders Approval Callback Handler` still handles Telegram `callback_query` updates for approval buttons.
