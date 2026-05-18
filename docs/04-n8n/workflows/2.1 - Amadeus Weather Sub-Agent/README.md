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
