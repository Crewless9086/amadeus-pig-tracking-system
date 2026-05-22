# ALERT - Weather Forecast

## Role

Scheduled weather forecast alert workflow.

Workflow ID: `I4D76Gb9ddGFhSP5`  
Status at import: inactive  
Imported for docs: 2026-05-18

## What It Does

- Runs on a schedule when active.
- Reads the 10-day forecast sheet.
- Filters the next three days.
- Builds forecast alert candidates.
- Reads prior alert log entries.
- Filters alerts by cooldown.
- Applies quiet-hours logic.
- Expands recipients.
- Sends Telegram alerts.
- Appends alert log rows.

## Main Data Sources

- `Amadeus_Weather_Logs`
- `Forecast_10Day_Current`
- `Weather_Alert_Log`

## Main Nodes

- `Schedule - Forecast Alerts`
- `Read Forecast_10Day_Current`
- `Filter Next 3 Days`
- `Build Forecast Alert Candidates`
- `Read Weather_Alert_Log`
- `Filter by Cooldown`
- `Quiet Hours`
- `Expand Recipients`
- `Send Sunsynk Alert`
- `Append Alert Log`

## Planning Notes

- The Telegram send node name still says `Send Sunsynk Alert`, but this workflow is for forecast alerts.
- This workflow is not directly part of Phase 7.3 order lookup, but it should be documented as part of Oom Sakkie operations.
- Phase 10.3L decision: do not make this Sheets-first workflow the future alert source of truth.
- Future direction: backend/Supabase should evaluate forecast alert candidates and cooldowns from `weather_forecast_snapshots` and `telemetry_alerts`; n8n should only call the backend evaluator and deliver approved Telegram alert messages.
- Keep this workflow inactive/documented until the backend alert evaluator is implemented and tested.
