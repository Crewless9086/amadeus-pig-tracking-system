# 2.2 - Amadeus Sunsynk Sub-Agent

## Role

Sunsynk solar and power sub-agent used by Oom Sakkie.

Workflow ID: `tKVKoCcxhT7CAydT`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by Oom Sakkie.
- Uses a LangChain agent for Sunsynk questions.
- Reads Sunsynk data through Google Sheets tools.
- Answers questions about current system state, daily summary, last 24 hours, and five-minute interval data.

## Main Data Sources

- `Amadeus_Sunsynk_Log`
- `Sunsynk_Current_Overview`
- `Sunsynk_Daily_Summary`
- `Sunsynk_Last24h_Hourly`
- `Sunsynk_5min_Intervals`

## Main Nodes

- `When Executed by Another Workflow`
- `AI Sunsynk Agent`
- `OpenAI Chat Model`
- `Sunsynk Current Overview`
- `Sunsynk Daily Summary`
- `Sunsynk Last24h Hourly`
- `Sunsynk 5min Intervals`

## Planning Notes

- This is already a sub-agent pattern similar to what the orders lookup tool should become.
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
