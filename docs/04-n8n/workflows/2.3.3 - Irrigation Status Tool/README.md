# 2.3.3 - Irrigation Status Tool

Read-only Oom Sakkie irrigation status tool.

Workflow ID: `rG7mN4pQ8sT2uV6w`  
Status at export: inactive until manually imported and tested  
Created for Phase 10.3Q: 2026-05-23

## Role

This workflow answers irrigation status questions for Oom Sakkie by calling the backend read-only irrigation status endpoint.

It must never control irrigation hardware.

## Backend Endpoint Used

```text
GET https://amadeus-pig-tracking-system.onrender.com/api/telemetry/irrigation/status
```

## Nodes

- `When Executed by Another Workflow`
- `Code - Route Irrigation Question`
- `HTTP - Get Irrigation Status`
- `Code - Format Irrigation Answer`

## Allowed

- Read backend irrigation status.
- Summarize current state, today's plan, next-zone fields, recent events, and read-only safety flags.
- Warn when `STATE.next_zone_id` and computed priority/water-score next zone differ.

## Not Allowed

- No Telegram Trigger.
- No IFTTT.
- No Google Sheets nodes.
- No Supabase writes.
- No backend command endpoints.
- No plan rebuilds.
- No status updates.
- No zone start/stop/pause/resume actions.

## Safety Rule

This workflow returns status only. If the backend response ever reports unexpected control flags, the answer warns the operator and still does not trigger any control action.

## Manual Test Plan

1. Import this workflow first.
2. Run it manually with input `What is the irrigation status?`.
3. Confirm it calls `/api/telemetry/irrigation/status`.
4. Confirm the answer says read-only and cannot start/stop/change irrigation.
5. Confirm no IFTTT or hardware-control nodes exist.
6. Import the updated `2.0 - OOM SAKKIE - Amadeus Assistant Agent`.
7. Ask Oom Sakkie: `What is the irrigation status?`
8. Confirm the reply is status-only and no controller workflow executes.
