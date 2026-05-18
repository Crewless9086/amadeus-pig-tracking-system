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
