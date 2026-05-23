# ALERT - Weather Backend Delivery

## Role

Thin Telegram delivery workflow for backend-owned weather alerts.

Status at export: inactive  
Created for docs: 2026-05-22  
Phase: 10.3L4

## What It Does

- Runs on a schedule when active.
- Calls the backend weather alert evaluator.
- Reads only backend `sendable_alerts`.
- Filters out test/audit alerts.
- Formats approved weather alerts.
- Sends Telegram alerts to Charl only in the first trial.

## What It Must Not Do

- Must not read Google Sheets.
- Must not write `Weather_Alert_Log`.
- Must not calculate weather thresholds in n8n.
- Must not calculate cooldowns in n8n.
- Must not deliver `BACKEND_AUDIT_TEST`.
- Must not deliver any alert where `details.test = true`.
- Must not use the old multi-recipient alert list until the Charl-only trial is accepted.

## Backend Source

Endpoint:

`POST https://amadeus-pig-tracking-system.onrender.com/api/telemetry/weather/alerts/evaluate`

Header:

`X-Amadeus-Telemetry-Key`

n8n Cloud blocks `$env` access in this workflow, so do not use an env-var expression in the HTTP node.

In `HTTP - Evaluate Weather Alerts`, set the header value manually:

- Header name: `X-Amadeus-Telemetry-Key`
- Header value: the same `TELEMETRY_INGEST_API_KEY` value configured on Render
- Important: use the plain value, not `={{$env.TELEMETRY_INGEST_API_KEY}}`

## Main Nodes

- `Schedule - Weather Alert Delivery`
- `Code - Build Evaluate Request`
- `HTTP - Evaluate Weather Alerts`
- `Code - Extract Sendable Alerts`
- `Code - Format Telegram Weather Alerts`
- `Telegram - Send Weather Alert`

## Manual Test Plan

1. Import inactive.
2. Confirm `Code - Build Evaluate Request` has `dryRun = true`.
3. In `HTTP - Evaluate Weather Alerts`, replace `PASTE_TELEMETRY_INGEST_API_KEY_HERE` with the real key.
4. Run manually and confirm no Telegram message is sent.
5. Temporarily set `includeTestAlert = true` while `dryRun = true`.
6. Run manually and confirm `BACKEND_AUDIT_TEST` is filtered out and no Telegram message is sent.
7. Set `dryRun = false` and `includeTestAlert = false`.
8. Run manually once.
9. Activate schedule only after the manual live run returns no alerts or expected real alerts.

## Planning Notes

- Backend/Supabase is the alert source of truth.
- n8n is only the delivery layer.
- Legacy weather alert workflow exports were removed after this path was live-verified. Do not reintroduce the old Sheets-first alert workflows.
