# 2.0 - OOM SAKKIE - Amadeus Assistant Agent

## Role

Main Oom Sakkie Telegram assistant workflow.

Workflow ID: `6UscGE44eTfdLp1A`  
Live status: active; read-only lookup live. Local 7.3D quote-send context changes pending backend deploy/import.  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by `2 - The GateKeeper`.
- Uses a LangChain agent as the main assistant brain.
- Sends replies back to Telegram.
- Uses memory for the assistant conversation.
- Calls weather, Sunsynk, and read-only order lookup sub-agents as tools.

## Main Nodes

- `When Executed by Another Workflow`
- `AI Assistant Agent`
- `AI Replay Agent`
- `Brain ChatGPT`
- `Replay ChatGPT`
- `Simple Memory`
- `Weather_Info_Tool`
- `Sunsynk_Info_Tool`
- `Orders_Info_Tool`
- `Send Replay`

## Tools / Sub-Workflows

- `2.1 - Amadeus Weather Sub-Agent` (`L4c34rFmN0kUJvWc`)
- `2.2 - Amadeus Sunsynk Sub-Agent` (`tKVKoCcxhT7CAydT`)
- `2.4.4 - Order Lookup Tool` (`1VNdetSbgP0ffNyH`)

## Planning Notes

- Phase 7.3 adds order lookup as a read-only tool first.
- `Orders_Info_Tool` passes the full operator message plus Telegram user/chat context to `2.4.4`, which owns safe lookup parsing, backend calls, and quote-send button preparation.
- n8n API upload of this active workflow failed with a server-side 500 even when attempting to PUT the unchanged live export. The 2026-05-18 update was completed through the n8n UI and read back into this repo.
- Order lookup must stay read-only until the later document-send guard phase is planned.
- Access remains controlled by `2 - The GateKeeper`.
