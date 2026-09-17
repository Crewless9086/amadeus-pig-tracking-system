# 2 - The GateKeeper

## Role

Live Telegram access gate for Oom Sakkie.

Workflow ID: `s8QaxmqT69Z5mhvE`  
Status: active and live-tested on 2026-05-19  
Imported for docs: 2026-05-19

## What It Does

- Receives Telegram `message` and `callback_query` updates.
- Normalizes inbound Telegram identity and callback fields.
- Reads the `ASSISTANT_USERS` sheet from the `Amadeus_Users` spreadsheet.
- Normalizes the authorization check.
- Routes unauthorized users to a Telegram rejection message.
- Routes authorized normal messages to `2.0 - OOM SAKKIE - Amadeus Assistant Agent`.
- Routes authorized approval callbacks to `2.4 - Amadeus Orders Sub Agent`.
- Routes authorized quote-send/cancel callbacks to `2.4.5 - Document Send Callback Handler`.

## Main Nodes

- `Telegram Trigger`
- `Code - Normalize Telegram Update`
- `Get User Info`
- `Normalize Auth Check`
- `Security Check`
- `Switch - Telegram Update Type`
- `Code - Normalize Telegram Callback`
- `Switch - Route Telegram Callback Type`
- `Answer Telegram Callback`
- `Send Not Authorized`
- `Call '2.0 - OOM SAKKIE - Amadeus Assistant Agent'`
- `Call 2.4 - Approval Callback Worker`
- `Call 2.4.5 - Document Send Callback Worker`

## Calls

- Calls workflow `2.0 - OOM SAKKIE - Amadeus Assistant Agent` (`6UscGE44eTfdLp1A`).
- Calls workflow `2.4 - Amadeus Orders Sub Agent` (`T8LLCAtYDLNRPoRx`) for approval callbacks.
- Calls workflow `2.4.5 - Document Send Callback Handler` (`8b14lAqmyrD0LYZz`) for quote-send/cancel callbacks.

## Planning Notes

- This workflow is the correct entry point for operator access control.
- Oom Sakkie planning should preserve this gate and not expose the main assistant directly.
- Any new Oom Sakkie order lookup capability should remain behind this gate.

## Telegram Routing Note

2026-05-18:

- This workflow owns normal Telegram `message` updates and button `callback_query` updates for Oom Sakkie.
- Both normal messages and button callbacks must pass authorization before routing.
- The conflicting normal-message trigger in `2.4 - Amadeus Orders Sub Agent` was disabled because it intercepted general Oom Sakkie messages before they reached this GateKeeper.
- `2.4.2 - Orders Approval Callback Handler` is inactive because a second active Telegram callback trigger can take over the bot webhook. GateKeeper now routes approval callbacks to `2.4` and quote-send callbacks to `2.4.5`.
- Edit this workflow through the n8n UI only. API workflow updates have failed unpredictably for GateKeeper and should not be used for live edits.
- If Oom Sakkie goes silent while GateKeeper still looks active in n8n, check Telegram `getWebhookInfo`; GateKeeper may need to be deactivated and reactivated in the n8n UI to force Telegram webhook registration.

2026-05-19:

- Owner manually uploaded the cleaned GateKeeper workflow and replaced the Telegram Trigger node in n8n.
- Live test passed: Telegram `Hi` reached GateKeeper, routed through `2.0`, and Oom Sakkie replied.
- The repo export has been refreshed from the live n8n workflow so future imports keep the current trigger node.

2026-06-14:

- Owner approved moving toward a live Telegram reply test through the Flask backend.
- Do not replace this workflow from the repo export for that test.
- First import `2.0B - Oom Sakkie Backend Read-Only Relay` inactive.
- Then follow `BACKEND_RELAY_WIRING_PLAN.md` in the n8n UI: keep this workflow as the only Telegram Trigger owner, replace only the normal-message call target, validate the backend no-authority flags, and send exactly one guarded owner reply from GateKeeper.

## SAM Live Callback Ownership Candidate (2026-07-25)

This source export contains a review-only correction; it has not been imported or activated live.

- GateKeeper remains the only Telegram ingress and authorization owner.
- Every `sam_live_*` callback is classified as `route_sam_live_callback` and relayed unchanged, as the original `raw_update`, to `POST /api/oom-sakkie/channels/telegram/direct-webhook`.
- The backend/Oom Sakkie handler is the only component allowed to interpret SAM Live callback actions, bind the exact review/card identity, change Chatwoot mode, send through the owner-send rail, or edit/delete the exact card.
- GateKeeper does not acknowledge SAM callbacks itself; the backend acknowledges them once without a separate Telegram message.
- Order approval and document-send callback families retain their existing workers.
- Unknown callback families are acknowledged as unsupported and never enter legacy Orders approval parsing.
- Import requires the n8n variable `OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET` to match the existing backend webhook secret. The value must never be exported or logged.
- Rollback is the prior GateKeeper export; no backend, database, Render, or Telegram migration is required.