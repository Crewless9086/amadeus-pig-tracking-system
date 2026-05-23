# 2.0 - OOM SAKKIE - Amadeus Assistant Agent

## Role

Main Oom Sakkie Telegram assistant workflow.

Workflow ID: `6UscGE44eTfdLp1A`  
Live status: active; 7.3D quote-send context update imported through n8n UI on 2026-05-18 because API update returns HTTP 500.  
Imported for docs: 2026-05-18

## What It Does

- Runs when called by `2 - The GateKeeper`.
- Uses a LangChain agent as the main assistant brain.
- Sends replies back to Telegram.
- Calls weather, Sunsynk, read-only irrigation status, and order lookup sub-agents as tools.
- Does not use assistant memory for operational routing; stale memory can cause tool-backed actions to be skipped.

## Main Nodes

- `When Executed by Another Workflow`
- `AI Assistant Agent`
- `AI Replay Agent`
- `Brain ChatGPT`
- `Replay ChatGPT`
- `Weather_Info_Tool`
- `Sunsynk_Info_Tool`
- `Irrigation_Info_Tool`
- `Orders_Info_Tool`
- `Switch - Suppress Direct Tool Reply`
- `Send Replay`

## Tools / Sub-Workflows

- `2.1 - Amadeus Weather Sub-Agent` (`L4c34rFmN0kUJvWc`)
- `2.2 - Amadeus Sunsynk Sub-Agent` (`tKVKoCcxhT7CAydT`)
- `2.3.3 - Irrigation Status Tool` (`rG7mN4pQ8sT2uV6w`)
- `2.4.4 - Order Lookup Tool` (`1VNdetSbgP0ffNyH`)

## Planning Notes

- Phase 7.3 adds order lookup as a read-only tool first.
- `Orders_Info_Tool` passes the full operator message plus Telegram user/chat context to `2.4.4`, which owns safe lookup parsing, backend calls, and quote-send button preparation.
- n8n API upload of this active workflow failed with a server-side 500. The `2.0` workflow was imported/updated through the n8n UI before testing quote-send buttons.
- Order lookup remains read-only except for guarded quote-send preparation, which only shows operator buttons and does not send until the callback worker confirms through the backend.
- Access remains controlled by `2 - The GateKeeper`.
- 2026-05-19: `Simple Memory` was disconnected after repeated quote-send preparation requests were answered from memory without calling `Orders_Info_Tool`.
- 2026-05-19: `Switch - Suppress Direct Tool Reply` was added locally. When a tool returns `__NO_TELEGRAM_REPLY__`, `2.0` suppresses its normal reply because the worker has already sent the direct Telegram button message.
- 2026-05-23: `Irrigation_Info_Tool` was added locally for read-only irrigation status only. It points to `2.3.3 - Irrigation Status Tool`, which calls the backend status endpoint and cannot start, stop, pause, resume, rebuild, or change irrigation.
