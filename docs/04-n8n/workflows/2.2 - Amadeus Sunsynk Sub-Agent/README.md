# 2.2 - Amadeus Sunsynk Sub-Agent

## Role

Sunsynk solar and power sub-agent used by Oom Sakkie.

Workflow ID: `tKVKoCcxhT7CAydT`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by Oom Sakkie.
- Routes the operator question to the backend current-power or recent-power endpoint.
- Formats a complete operator-ready power answer.
- Answers current/live power state questions: battery, solar/PV, load, grid, generator, and data freshness.
- Answers recent/last-24h trend questions from sample-based Supabase power readings.
- Keeps kWh, cost, import, and export totals clearly limited until approved energy counters or interval-integration rules are added.
- Does not use a LangChain agent loop or Google Sheets tools anymore.

## Main Data Sources

- Backend endpoints:
  - `GET /api/telemetry/power/current`
  - `GET /api/telemetry/power/recent?hours=24`
- Backend source: Supabase `power_latest_state` and `power_readings_5min`
- Logger source: Render cron `amadeus-sunsynk-logger`

## Main Nodes

- `When Executed by Another Workflow`
- `Code - Route Power Question`
- `HTTP - Get Power Data`
- `Code - Format Power Answer`

## Planning Notes

- This workflow is now a deterministic backend-read worker, not an LLM sub-agent.
- Current-state and sample-based recent/last-24h power profile questions are supported.
- Daily totals, kWh, import/export energy totals, and cost answers need later backend energy-counter or approved interval-integration read models before they are enabled as confirmed totals.
- Keep solar/power data ownership separate from orders.

## Known Issue Log

- 2026-05-19: Owner reported that Sunsynk/power questions were not reliably returning results through Oom Sakkie.
- Live execution `45137` was called with valid input (`What's the power like now?`) but was cancelled after about three minutes. The run reached `Sunsynk Current Overview` and did not produce a final agent response.
- Prepared fix:
  - `2.0` `Sunsynk_Info_Tool` passes the user power question with n8n `$fromAI('sunsynk_question', ...)`.
  - `AI Sunsynk Agent` has a fallback prompt (`current power status at the farm`).
  - `AI Sunsynk Agent` has `maxIterations = 4` and an explicit instruction to answer after one primary tool call.
- Owner retest after hardening still ran too long and was manually cancelled.
- Decision: do not keep tweaking the agent loop now. Defer to a dedicated Sunsynk data/backend/Supabase architecture review.
- Follow-up review must inventory the Sunsynk Google Sheets tabs, any backend modules/scripts, `ALERT - Sunsynk`, data volume, current read patterns, and whether a small backend API backed by Supabase/Postgres should replace direct agent reads from large Sheets.
- 2026-05-22: Rebuilt `2.2` to call `GET /api/telemetry/power/current` and format the backend payload directly. Removed the Google Sheets tools and LangChain agent loop from the workflow export.
- 2026-05-22: Live Telegram test passed after import. `What's the power like now?` returned quickly with current backend/Supabase data: battery `46%` discharging, solar `0.0 kW`, load `1.0 kW`, grid not using grid, generator off, and latest reading `22 May 2026, 00:40` at `4 minutes old`.
- 2026-05-22: Prepared `10.3I` workflow update. `2.2` now routes current questions to `/api/telemetry/power/current` and recent/trend questions to `/api/telemetry/power/recent?hours=24`. Energy-total questions get a clear sample-based limitation instead of invented kWh/cost/import/export totals.
- 2026-05-22: Live Telegram tests passed after import. Current power, last-24h profile, last-night grid use, and solar-total limitation wording all worked. Minor future polish: recent-profile answers can repeat the sample-based limitation because backend notes and workflow formatting both include it.
