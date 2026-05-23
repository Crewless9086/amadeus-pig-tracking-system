# 2.3.1 - Build Daily Irrigation Plan

## Role

Daily irrigation planning workflow.

Workflow ID: `UNwNmx0TwtFf8mjo`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs on a daily schedule at `00:05`.
- Reads irrigation zones and rules.
- Reads the current 24-hour weather forecast summary.
- Builds daily irrigation plan rows.
- Checks whether a plan already exists for today.
- Appends the daily plan when needed.
- Updates irrigation state and appends a log row.

## Main Data Sources

- `Amadeus_Irrigation_Logs`
- `ZONES`
- `RULES`
- `DAILY_PLAN`
- `STATE`
- `LOG`
- `Amadeus_Weather_Logs`
- `Forecast_24hr_Current`

## Main Nodes

- `A1 - Daily 00:05 Trigger`
- `A2 - Get ZONES`
- `A3 - Get RULES`
- `A4 - Get Forecast_24h Summary`
- `A5 - Build DAILY_PLAN Rows`
- `A6 - Check Existing Plan (Today)`
- `A7 - If Plan Exists, Stop`
- `A8 - Append DAILY_PLAN`
- `A9 - Update STATE`
- `A10 - Append LOG`

## Planning Notes

- This is operational automation, not assistant conversation.
- It writes to irrigation sheets and should be treated as a controlled automation workflow.
- It is outside Phase 7.3 order lookup, but it belongs in the broader Oom Sakkie operating system documentation.
- Phase 10.3O status: keep this workflow stable while irrigation command/audit planning is done. Do not expand it into hardware-control behavior in this slice.
