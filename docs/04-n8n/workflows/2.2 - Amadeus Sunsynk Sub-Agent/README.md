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
