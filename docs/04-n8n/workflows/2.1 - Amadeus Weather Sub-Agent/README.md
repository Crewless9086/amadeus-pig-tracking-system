# 2.1 - Amadeus Weather Sub-Agent

## Role

Weather sub-agent used by Oom Sakkie.

Workflow ID: `L4c34rFmN0kUJvWc`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by Oom Sakkie.
- Routes the weather question deterministically.
- Calls the backend current weather endpoint for current/now weather questions.
- Calls the backend today summary endpoint for today/daily/rain-today weather questions.
- Calls the backend forecast endpoint for forecast/tomorrow/coming-weather questions.
- Formats the backend response into a user-ready answer.
- Returns `answer`, `output`, and `weather_response` for compatibility with Oom Sakkie.
- Does not use LangChain/OpenAI nodes or Google Sheets reads in this workflow.

## Main Data Sources

- `GET /api/telemetry/weather/current`
- `GET /api/telemetry/weather/today`
- `GET /api/telemetry/weather/forecast?days=3`
- Backend reads from Supabase weather read models populated by the weather and forecast Render cron loggers.

## Main Nodes

- `When Executed by Another Workflow`
- `Code - Route Weather Question`
- `HTTP - Get Weather Data`
- `Code - Format Weather Answer`

## Planning Notes

- This is already structured as a sub-agent and should remain separate from order lookup.
- Oom Sakkie can continue using this as a weather tool while Phase 7.3 adds an orders tool.
- Phase 10.3J simplified this workflow after the weather and forecast backend endpoints were deployed and logger-verified.
- Keep Google Sheets weather alert workflows separate until alert alignment is planned.

## Known Issue Log

- 2026-05-19: Owner reported live LLM errors in this workflow. Logged as Phase 7.3E quick triage in `docs/00-start-here/NEXT_STEPS.md`.
- Triage should first identify the failing node and cause before editing: credential/model issue, malformed LLM JSON output, missing upstream sheet data, or n8n node-version behavior.
- Keep fixes contained to this weather workflow or its direct forecast/data dependencies unless the execution evidence shows a wider Oom Sakkie routing issue.
- Diagnosis from live executions:
  - `45114`, `45118`, `45120`: `Weather Router (JSON Plan)` failed because `chatgpt-4o-latest` was rejected by OpenAI.
  - `45121`, `45123`, `45125`: same node failed because the prompt text was `null`.
  - `45125` showed fresh station data, so the issue was the `2.0 -> 2.1` tool handoff and router prompt fallback, not the weather sheet.
- Prepared fix:
  - `2.0` `Weather_Info_Tool` should pass the user question with n8n `$fromAI('weather_question', ...)`.
  - `2.1` `Weather Router (JSON Plan)` should use `gpt-5.5` and a non-null fallback prompt.
  - Workflow contract tests now guard both rules.
- 2026-05-22: Phase 10.3J replaced the old Sheets/LLM-heavy path with a deterministic backend read workflow.
  - Current weather now comes from `/api/telemetry/weather/current`.
  - Today weather summary now comes from `/api/telemetry/weather/today`.
  - Forecast now comes from `/api/telemetry/weather/forecast?days=3`.
  - Old nodes `Weather Router (JSON Plan)`, `Weather Answer LLM (JSON only)`, `Precheck - Latest Station Row`, `Read Forecast_10Day_Current`, and `Read Daily_Pivot` are intentionally removed from this workflow export.
