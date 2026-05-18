# ALERT - Local Weather Station

## Role

Scheduled local weather station alert workflow.

Workflow ID: `g0ajlm9gBp7J72Jn`  
Status at import: inactive  
Imported for docs: 2026-05-18

## What It Does

- Runs on a schedule when active.
- Reads latest and today's weather station data.
- Builds weather alert candidates.
- Reads previous alert log data.
- Filters alerts by cooldown.
- Applies quiet-hours logic.
- Expands recipients.
- Sends Telegram alerts.
- Appends alert log rows.

## Main Data Sources

- `Amadeus_Weather_Logs`
- `LLM_Latest_Reading`
- `LLM_Today_Readings`
- `Weather_Alert_Log`

## Main Nodes

- `Schedule - Weather Station Alerts`
- `Get LLM_Latest_Reading (Weather)`
- `Get LLM_Today_Readings (Weather)`
- `Normalize Weather + Station Age`
- `Build Weather Alert Candidates`
- `Read Weather_Alert_Log`
- `Filter by Cooldown`
- `Quiet Hours`
- `Expand Recipients`
- `Send Sunsynk Alert`
- `Append Alert Log`

## Planning Notes

- The Telegram send node name still says `Send Sunsynk Alert`, but this workflow is for local weather station alerts.
- This workflow is not directly part of Phase 7.3, but it is part of the Oom Sakkie operational ecosystem.
