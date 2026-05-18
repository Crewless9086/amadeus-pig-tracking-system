# 2.3.2 - Run Irrigation Controller

## Role

Irrigation controller workflow that starts and stops irrigation zones.

Workflow ID: `f6oPLsaolGH4pMKC`  
Status at import: inactive  
Imported for docs: 2026-05-18

## What It Does

- Runs on a schedule when active.
- Reads irrigation state, rules, weather, zones, and today's daily plan.
- Decides whether to start or stop a zone.
- Calls IFTTT webhooks for zone on/off control.
- Updates `DAILY_PLAN` and `STATE`.
- Appends irrigation log rows.

## Main Data Sources

- `Amadeus_Irrigation_Logs`
- `STATE`
- `RULES`
- `ZONES`
- `DAILY_PLAN`
- `LOG`
- `Amadeus_Weather_Logs`
- `LLM_Latest_Reading`

## Main Nodes

- `B1 - Schedule Trigger`
- `B2 - Get STATE`
- `B3 - Get RULES`
- `B4 - Get Weather Now`
- `B5 - Get TODAY DAILY_PLAN`
- `B6 - Code: Decide action`
- `B8A - HTTP START_ZONE (IFTTT ON)`
- `B8B - HTTP STOP_ZONE (IFTTT OFF)`
- `B9A - Update DAILY_PLAN to RUNNING`
- `B9B - Update DAILY_PLAN to DONE`
- `B10A - Update STATE to RUNNING`
- `B10B - Update STATE to IDLE`
- `B11A/B - Append LOG`

## Safety Notes

- This workflow can control real irrigation hardware through IFTTT.
- The imported workflow contains direct IFTTT webhook URL expressions. Treat this export as private and move the key into a protected credential or environment value before wider sharing.
- Do not activate or edit this workflow casually.

## Credential / Secret Handling Plan

Short-term:

- Move the IFTTT Maker key out of the HTTP node URL expression.
- Prefer n8n credential storage if it can cleanly inject the key into the HTTP request.
- If n8n credential storage is awkward for this URL shape, use protected n8n environment variables:
  - `IFTTT_BASE_URL`
  - `IFTTT_MAKER_KEY`
- Keep only event names such as `ifttt_on_event` and `ifttt_off_event` in Google Sheets/workflow data.

Medium-term:

- Replace direct n8n-to-IFTTT calls with backend-controlled irrigation endpoints.
- Suggested backend shape:
  - `POST /api/irrigation/zones/<zone_id>/start`
  - `POST /api/irrigation/zones/<zone_id>/stop`
- Backend should own the IFTTT key, zone validation, cooldowns, audit logs, safety locks, and error handling.
- n8n should request a zone action from the backend instead of holding hardware-control secrets.

## Planning Notes

- This workflow is not part of Phase 7.3 order lookup.
- Any future Oom Sakkie irrigation commands should require strong confirmation and safety checks.
- Track the credential migration as a future security/hardware-control hardening task before expanding irrigation automation.
