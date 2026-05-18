# 2.0 - OOM SAKKIE - Amadeus Assistant Agent

## Role

Main Oom Sakkie Telegram assistant workflow.

Workflow ID: `6UscGE44eTfdLp1A`  
Status at import: active  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by `2 - The GateKeeper`.
- Uses a LangChain agent as the main assistant brain.
- Sends replies back to Telegram.
- Uses memory for the assistant conversation.
- Calls weather and Sunsynk sub-agents as tools.

## Main Nodes

- `When Executed by Another Workflow`
- `AI Assistant Agent`
- `AI Replay Agent`
- `Brain ChatGPT`
- `Replay ChatGPT`
- `Simple Memory`
- `Weather_Info_Tool`
- `Sunsynk_Info_Tool`
- `Send Replay`

## Tools / Sub-Workflows

- `2.1 - Amadeus Weather Sub-Agent` (`L4c34rFmN0kUJvWc`)
- `2.2 - Amadeus Sunsynk Sub-Agent` (`tKVKoCcxhT7CAydT`)

## Planning Notes

- This is the correct place to add Oom Sakkie order lookup as a tool, but not before the order lookup contract is accepted.
- The current workflow does not yet call the orders sub-agent as a LangChain tool.
- Phase 7.3 should add order lookup as read-only first.
- Access remains controlled by `2 - The GateKeeper`.
