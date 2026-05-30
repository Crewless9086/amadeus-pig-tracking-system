# ALERT - Farm Attention Digest

Thin Telegram delivery workflow for backend-owned farm attention summaries.

Status: active in n8n / manual send verified  
Created for docs: 2026-05-30  
Phase: 10 farm attention follow-up

## Role

This workflow sends a digest of important farm attention items to Charl so they are visible even when the web app has not been opened.

The backend owns:

- order attention rules
- litter attention rules
- digest source data
- read-only source contract

n8n owns only:

- schedule
- backend call
- dry-run/manual activation safety
- simple delivery throttling/change detection
- Telegram delivery

## Backend Endpoint

Endpoint:

`GET https://amadeus-pig-tracking-system.onrender.com/api/reports/farm-attention-summary?limit=10`

Expected backend flags:

- `mode = read_only`
- `source.writes_to_supabase = false`
- `source.writes_to_sheets = false`
- `source.sends_telegram = false`

## Main Nodes

- `Schedule - Farm Attention Digest`
- `Code - Build Attention Request`
- `HTTP - Get Farm Attention Summary`
- `Code - Extract Sendable Digest`
- `Code - Format Telegram Farm Attention Digest`
- `Telegram - Send Farm Attention Digest`
- `Code - Record Sent Digest`

## Safety Rules

- Workflow export stays inactive by default.
- `Code - Extract Sendable Digest` starts with `dryRun = true`; no Telegram message should send until this is deliberately changed.
- Do not send when `attention_total <= 0`.
- Do not send if backend flags indicate writes or Telegram sending happened inside the backend call.
- Do not repeat the same digest content hash once workflow static data has been recorded by a non-manual execution.
- Do not send more often than the configured minimum hours unless `forceSend = true` is deliberately set for a manual test.
- Keep first live recipient scope to Charl only.
- Static-data duplicate suppression is recorded after Telegram delivery succeeds. n8n manual executions may not persist workflow static data, so repeated manual tests can still send again.

## Manual Test Plan

1. Import inactive.
2. Keep `dryRun = true`.
3. Run manually and confirm no Telegram message is sent.
4. Inspect `HTTP - Get Farm Attention Summary` output and confirm `success = true`, `mode = read_only`, and the three source flags are false.
5. If a live Telegram test is wanted, set `dryRun = false` and `forceSend = true`, then run manually once.
6. Confirm one Telegram digest is sent to Charl.
7. Set `forceSend = false`.
8. Do not rely on a second manual run to prove duplicate suppression. n8n manual executions may not persist workflow static data.
9. For a duplicate-suppression proof, activate the workflow with a short temporary schedule, let two scheduled executions run, and confirm the second scheduled execution stops at `Code - Extract Sendable Digest`.
10. Return the schedule to the approved interval before leaving the workflow live.

## Planning Notes

- This is a digest/reminder workflow, not an alert evaluator.
- Do not move order/litter attention rules into n8n.
- Do not read Google Sheets directly.
- Do not write Supabase or Google Sheets from this workflow.
- Future refinement can add severity grouping once backend attention items expose stable severity fields.

## Verification Notes

- n8n workflow ID: `kd5wrJEgBfUNNxnb`.
- 2026-05-30 API check confirmed the workflow is active.
- Execution `49136` stopped at `Code - Extract Sendable Digest` with zero output.
- Executions `49137` and `49138` reached `Telegram - Send Farm Attention Digest` and `Code - Record Sent Digest`.
- Sent digest content: `attention_total = 1`, `orders = 0`, `litters = 1`, `LIT-2026-8A0F: Piglets need tag numbers`.
- First scheduled duplicate-suppression observation is still pending; manual executions are not reliable proof because workflow static data may not persist from manual runs.
