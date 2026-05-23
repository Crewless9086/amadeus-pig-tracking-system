# ALERT - Power Backend Delivery

Thin Telegram delivery workflow for backend-owned Sunsynk/power alerts.

Status: active / live-verified  
Created for docs: 2026-05-23  
Phase: 10.3N

## Role

This workflow replaces the old `ALERT - Sunsynk` logic path.

The backend owns:

- power alert rules
- cooldowns
- quiet-hours policy
- duplicate prevention
- alert history in `telemetry_alerts`

n8n owns only:

- schedule
- backend call
- final safety filter
- Telegram delivery

## Backend Endpoint

Endpoint:

`POST https://amadeus-pig-tracking-system.onrender.com/api/telemetry/power/alerts/evaluate`

Header:

`X-Amadeus-Telemetry-Key`

n8n Cloud blocks `$env` access in this workflow, so do not use an env-var expression in the HTTP node.

In `HTTP - Evaluate Power Alerts`, set the header value manually:

- Header name: `X-Amadeus-Telemetry-Key`
- Header value: the same `TELEMETRY_INGEST_API_KEY` value configured on Render
- Important: use the plain value, not `={{$env.TELEMETRY_INGEST_API_KEY}}`

## Main Nodes

- `Schedule - Power Alert Delivery`
- `Code - Build Evaluate Request`
- `HTTP - Evaluate Power Alerts`
- `Code - Extract Sendable Alerts`
- `Code - Format Telegram Power Alerts`
- `Telegram - Send Power Alert`

## Manual Test Plan

1. [Done 2026-05-23] Import inactive.
2. [Done 2026-05-23] Confirm `Code - Build Evaluate Request` has `dryRun = true`.
3. [Done 2026-05-23] In `HTTP - Evaluate Power Alerts`, replace `PASTE_TELEMETRY_INGEST_API_KEY_HERE` with the real key.
4. [Done 2026-05-23] Run manually and confirm no Telegram message is sent.
5. [Done 2026-05-23] Temporarily set `includeTestAlert = true` while `dryRun = true`.
6. [Done 2026-05-23] Run manually and confirm `POWER_BACKEND_AUDIT_TEST` is filtered out and no Telegram message is sent.
7. [Done 2026-05-23] Set `dryRun = false` and `includeTestAlert = false`.
8. [Done 2026-05-23] Run manually once.
9. [Done 2026-05-23] Live execution `47565` sent `POWER_BATTERY_LOW` and wrote `ALT-C758569F3D95` to Supabase.

## Safety Rules

- Never deliver dry-run output.
- Never deliver `POWER_BACKEND_AUDIT_TEST`.
- Never deliver alerts where `details.test = true`.
- Do not calculate thresholds in n8n.
- Do not calculate cooldowns in n8n.
- Do not read Sunsynk Google Sheets.
- Do not write `Sunsynk_Alert_Log`.
- Keep first live recipient scope to Charl only.

## Legacy Workflow

`ALERT - Sunsynk` was removed from n8n and from the repo workflow exports after this workflow was live-verified. Do not keep both Sunsynk/power alert workflows live.
