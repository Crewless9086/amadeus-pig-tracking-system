# 2.2 - Amadeus Sunsynk Sub-Agent

## Role

Sunsynk solar and power sub-agent used by Oom Sakkie.

Workflow ID: `tKVKoCcxhT7CAydT`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by Oom Sakkie.
- Calls the backend current-power endpoint.
- Formats a complete operator-ready power answer.
- Answers current/live power state questions: battery, solar/PV, load, grid, generator, and data freshness.
- Does not use a LangChain agent loop or Google Sheets tools anymore.

## Main Data Sources

- Backend endpoint: `GET /api/telemetry/power/current`
- Backend source: Supabase `power_latest_state`
- Logger source: Render cron `amadeus-sunsynk-logger`

## Main Nodes

- `When Executed by Another Workflow`
- `HTTP - Get Current Power State`
- `Code - Format Current Power Answer`

## Planning Notes

- This workflow is now a deterministic backend-read worker, not an LLM sub-agent.
- Current-state power questions are supported first.
- Daily totals, kWh, last-24h trends, and interval analysis need later backend read models before they are re-enabled in Oom Sakkie.
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
