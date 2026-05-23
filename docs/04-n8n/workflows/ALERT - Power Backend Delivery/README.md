# ALERT - Power Backend Delivery

Thin Telegram delivery workflow for backend-owned Sunsynk/power alerts.

Status at export: inactive  
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

1. Import inactive.
2. Confirm `Code - Build Evaluate Request` has `dryRun = true`.
3. In `HTTP - Evaluate Power Alerts`, replace `PASTE_TELEMETRY_INGEST_API_KEY_HERE` with the real key.
4. Run manually and confirm no Telegram message is sent.
5. Temporarily set `includeTestAlert = true` while `dryRun = true`.
6. Run manually and confirm `POWER_BACKEND_AUDIT_TEST` is filtered out and no Telegram message is sent.
7. Set `dryRun = false` and `includeTestAlert = false`.
8. Run manually once.
9. Activate schedule only after the manual live run returns no alerts or expected real alerts.

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

`ALERT - Sunsynk` should remain live until this backend-driven path is imported, dry-run tested, live-tested, and accepted. After that it can be archived.
