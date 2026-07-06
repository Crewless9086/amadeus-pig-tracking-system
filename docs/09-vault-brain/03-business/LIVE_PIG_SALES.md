# Live Pig Sales

Status: existing business stream; backend-native SAM Live Stock automation is not live yet.

Live pig sales remain important and urgent because suitable animals that are not sold continue to consume feed and reduce margin.

This lane sits under Amadeus Farm Sales. SAM is the Farm Sales CEO. The Live Pig Sales Agent is the specialist under SAM.

## Business Purpose

Sell suitable live pigs through a controlled, source-backed process that protects margin without creating wrong promises.

The live-stock sales lane covers:

- piglets;
- weaners;
- growers;
- finishers;
- ready-for-slaughter live pigs;
- owner-approved breeding or replacement stock exceptions.

## Current Position

Meat Sales has a backend-native SAM runtime. Live Pig Sales does not yet have the same runtime.

The old n8n workflow contains useful behavior, but current implementation must use app/Supabase truth for stock, orders, intake, reservations, and sales records.

## Required Build Direction

Future work must connect:

- live pig availability;
- pig allocation readiness;
- customer demand;
- price rules;
- stock/reservation rules;
- order intake memory;
- owner review and approval gates;
- Chatwoot/WhatsApp policy gates.

## Source References

- `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md`
- `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md`
- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/05-playbooks/SAM_LIVE_STOCK_HUMAN_SALES_PLAYBOOK.md`
- `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`
- `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`
