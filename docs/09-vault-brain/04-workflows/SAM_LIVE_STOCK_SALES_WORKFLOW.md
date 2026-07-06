# SAM Live Stock Sales Workflow

Status: Stage 1 authority. This workflow is approved for planning, routing, and owner review only. It does not approve live customer automation, order creation, reservation, payment confirmation, or sales transaction writes.

## Purpose

SAM Live Stock Sales turns customer interest in live pigs into clean, source-backed sales opportunities. The workflow must reduce feed-pressure losses without creating wrong stock promises or confusing live-stock sales with meat sales.

## Lane Boundary

SAM must classify the sales lane before doing anything material:

- `meat_sales`: pork, carcass, cut sets, freezer packs, chops, roasts, mince, ribs, belly, delivery of meat;
- `live_stock_sales`: live pigs, piglets, weaners, growers, finishers, gilts, boars, sows, pigs to raise, pigs to buy alive;
- `slaughter_abattoir_sales`: assisted slaughter, abattoir, slaughter pig, kill/cut service, slaughter booking, ready-for-slaughter handoff;
- `farm_general_question`: general farm/product questions without buying intent;
- `owner_handoff`: complaint, dispute, special pricing, payment proof, refund, breeding exception, or customer asks for Charl/owner;
- `unclear`: mixed, vague, contradictory, or low-confidence intent.

Mixed meat/live-stock language must clarify before proceeding. Example: `I want pork and maybe two weaners` is not safe for a single lane.

## Operating Flow

1. Customer message arrives through Chatwoot/WhatsApp, manual owner capture, or a future campaign source.
2. SAM Sales Router classifies the lane.
3. If lane is not `live_stock_sales`, hand off to the correct lane or clarify.
4. If lane is live stock, collect only the next missing fact.
5. Load existing conversation/order-intake memory when the backend runtime exists.
6. Read current availability from backend source truth.
7. Prepare advisory next action, owner packet, or safe draft reply.
8. Backend/owner gates decide whether draft order, reservation, quote, or customer send may happen.
9. Append learning evidence after blocked, unclear, rejected, or corrected outcomes.

## Required Facts

Before a live-stock draft order can be prepared:

- customer name/phone/conversation id;
- confirmed live-stock lane;
- category or weight range;
- quantity;
- sex preference or no preference;
- timing;
- customer location and collection/delivery expectation;
- payment preference if discussed;
- availability check;
- active order/intake conflict check.

## Hard Gates

- No automatic stock reservation in the first version.
- No customer may be told a pig is held unless backend reservation succeeds.
- No price is final until the active price source and owner rules agree.
- No payment is confirmed from POP alone.
- No breeding candidate, sow, boar, or replacement-quality gilt may be offered without owner approval.
- No sold, exited, reserved, terminal, off-farm, withdrawal-blocked, or source-conflicted animal may be offered.
- No old n8n or Google Sheet value may override app/Supabase truth.

## Current Build Stage

Stage 1/2 delivers:

- Vault authority;
- source-map authority;
- deterministic no-write router/classifier;
- unit tests proving lane separation.

Future stages add backend runtime, intake writes, availability matching, draft order gates, Chatwoot smoke tests, and owner command-room visibility.

## Source References

- `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md`
- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md`
- `docs/09-vault-brain/03-business/LIVE_PIG_SALES.md`
- `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`
- `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`
- `modules/sales/sam_sales_router.py`
