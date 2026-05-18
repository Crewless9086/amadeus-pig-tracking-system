# 2.4.1 - Test Caller

## Role

Manual test caller for the orders sub-agent.

Workflow ID: `GwWZueB0iyonpscl`  
Status at import: inactive  
Imported for docs: 2026-05-18

## What It Does

- Runs manually.
- Builds a test payload.
- Calls `2.4 - Amadeus Orders Sub Agent`.

## Main Nodes

- `When clicking 'Execute workflow'`
- `Set - Test Payload`
- `Call '2.4A - Amadeus Orders Sub Agent'`

## Calls

- Calls workflow `2.4 - Amadeus Orders Sub Agent` (`T8LLCAtYDLNRPoRx`).

## Planning Notes

- This appears to be a testing utility, not production workflow logic.
- Keep it inactive unless deliberately testing.
- Update the workflow display name/reference later if the old `2.4A` label causes confusion.
