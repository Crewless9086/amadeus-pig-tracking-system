# 2.1.1 - Amadeus Forecast Tool

## Role

Small forecast utility workflow.

Workflow ID: `vx1lV8aFCG28KSIN`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by another workflow.
- Sets forecast inputs.
- Calls the Open-Meteo forecast API.
- Formats the daily forecast response.

## Main Nodes

- `When Executed by Another Workflow`
- `Set Forecast Inputs`
- `Get Forecast (Open-Meteo)`
- `Format Daily Forecast`

## External Services

- Open-Meteo forecast API.

## Planning Notes

- This is a focused utility workflow and should stay separate from the broader `2.1` weather sub-agent.
- It is not directly related to Phase 7.3 order lookup, but it is part of the Oom Sakkie ecosystem.

## Known Issue Log

- 2026-05-19: Owner reported forecast-related behavior was not loading/returning reliably.
- n8n execution history showed no recent `2.1.1` executions, so the current `2.1` weather path is not calling this utility workflow. Current `2.1` reads `Forecast_10Day_Current` directly.
- Prepared hardening:
  - Optional `offsetDays`, `startOffsetDays`, and `endOffsetDays` inputs now default to blank strings instead of raw null values.
  - Workflow contract tests guard those defaults.
- Open design decision: decide later whether `2.1` should call `2.1.1` again as the forecast worker, or whether `2.1.1` should remain a standalone/manual forecast utility while `2.1` uses the forecast sheet.
