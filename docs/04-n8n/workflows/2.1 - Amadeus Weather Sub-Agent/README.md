# 2.1 - Amadeus Weather Sub-Agent

## Role

Weather sub-agent used by Oom Sakkie.

Workflow ID: `L4c34rFmN0kUJvWc`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by Oom Sakkie.
- Reads the latest weather station row.
- Checks station status.
- Uses an LLM router to decide whether daily pivot and/or forecast data is needed.
- Reads weather forecast and daily pivot sheets when needed.
- Assembles a weather payload.
- Uses an LLM to produce a JSON-only weather answer.

## Main Data Sources

- `Amadeus_Weather_Logs`
- `LLM_Latest_Reading`
- `Forecast_10Day_Current`
- `Daily_Pivot`

## Main Nodes

- `When Executed by Another Workflow`
- `Precheck - Latest Station Row`
- `Precheck - Station Status`
- `Weather Router (JSON Plan)`
- `Need Daily Pivot?`
- `Need Forecast?`
- `Read Forecast_10Day_Current`
- `Read Daily_Pivot`
- `Assemble Weather Payload`
- `Weather Answer LLM (JSON only)`
- `Set Response`

## Planning Notes

- This is already structured as a sub-agent and should remain separate from order lookup.
- Oom Sakkie can continue using this as a weather tool while Phase 7.3 adds an orders tool.

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
