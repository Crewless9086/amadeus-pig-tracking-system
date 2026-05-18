# ALERT - Sunsynk

## Role

Scheduled Sunsynk alert workflow.

Workflow ID: `2LETWzde7lMDlMnl`  
Status at import: inactive  
Imported for docs: 2026-05-18

## What It Does

- Runs on a schedule when active.
- Reads the latest Sunsynk overview row.
- Builds alert candidates.
- Reads previous alert log data.
- Filters alerts by cooldown.
- Applies quiet-hours logic.
- Expands recipients.
- Sends Telegram alerts.
- Appends alert log rows.

## Main Data Sources

- `Amadeus_Sunsynk_Log`
- `Sunsynk_Current_Overview`
- `Sunsynk_Alert_Log`

## Main Nodes

- `Schedule - Sunsynk Alerts`
- `Get Last Sunsynk Row`
- `Latest Row + Normalize`
- `Build Alert Candidates`
- `Read Sunsynk_Alert_Log`
- `Filter by Cooldown`
- `Quiet Hours`
- `Expand Recipients`
- `Send Sunsynk Alert`
- `Append Alert Log`

## Planning Notes

- This is alert automation, not Oom Sakkie conversation handling.
- It should stay separate from the `2.2` Sunsynk sub-agent, which answers questions on demand.
