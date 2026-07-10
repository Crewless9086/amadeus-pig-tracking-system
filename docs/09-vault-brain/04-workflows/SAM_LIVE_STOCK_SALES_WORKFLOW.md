# SAM Live Stock Sales Workflow

Status: Current authority. SAM Live Stock may create backend draft orders when source truth, fact completeness, availability, and pricing gates pass. It does not reserve stock, confirm payment, send quotes, or make final customer promises without the relevant backend/owner gates.

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
8. If all facts, full availability, and active pricing are present, SAM may create a draft order through the backend order rail.
9. Backend/owner gates decide whether reservation, quote, customer send, or payment-dependent actions may happen.
10. Append learning evidence after blocked, unclear, rejected, or corrected outcomes.
11. If the customer becomes hostile, repeatedly demands the exact farm location, calls the farm a scam, or aggressively challenges pricing, SAM should close politely, stop replying, and escalate/log the conversation for owner visibility.

## Requested Delivery Planning

SAM must stay collection-first. Normal live-stock stock, price, and availability replies must not advertise delivery or transport.

If the customer explicitly asks about delivery, transport, drop-off, or being far away, SAM may capture delivery planning facts for owner review:

- destination town, address, or location;
- one-way kilometres from Riversdale to that destination;
- delivery fee estimate at R20 per one-way kilometre;
- total estimate combining livestock plus delivery when livestock price is available.

If the delivery destination is missing, SAM asks only where delivery would need to go. If the destination is known but one-way kilometres are missing, SAM asks only for the one-way kilometre distance. Delivery wording must remain an estimate and must not promise driver availability, timing, final delivery approval, or final total.

Owner-review packets for delivery requests must surface: delivery requested, destination, one-way km, delivery fee estimate, total with livestock plus delivery, and an owner override warning. Owner corrections to delivery estimates or wording should be preserved as learning evidence for future SAM review.

## Required Facts

Before a live-stock draft order can be prepared:

- customer name/phone/conversation id;
- confirmed live-stock lane;
- category or weight range;
- quantity;
- sex preference or no preference;
- timing;
- handover location: Riversdale, Albertinia, or owner-reviewed exception;
- payment preference if discussed;
- availability check;
- active order/intake conflict check.

## Hard Gates

- Draft order auto-create is allowed only when the draft gate passes.
- No automatic stock reservation.
- No customer may be told a pig is held unless backend reservation succeeds.
- Price source is `public.sales_pricing`, inherited from `SALES_PRICING`, edited through `/sales/sam-pricing`, and resolved by effective date.
- No payment is confirmed from POP alone.
- No breeding candidate, sow, boar, or replacement-quality gilt may be offered through the normal live-stock sale lane.
- Only source-truth `Purpose = Sale` pigs may be offered.
- No sold, exited, reserved, terminal, off-farm, withdrawal-blocked, or source-conflicted animal may be offered.
- No old n8n or Google Sheet value may override app/Supabase truth.
- Do not share the exact farm location. Live-stock handover is Riversdale or Albertinia after the order path is confirmed.
- Do not argue about scam accusations, exact location, or pricing. Close politely and escalate/log when the buyer is rude, aggressive, or already negative.
- Do not send repeated closing replies after the customer has naturally ended the conversation.

## Current Build Stage

Current build delivers:

- Vault authority;
- source-map authority;
- deterministic router/classifier;
- backend read context;
- intake write rail;
- availability matching;
- pricing evidence;
- draft order gate;
- owner action packet;
- unit tests proving lane separation, pricing, draft order, and no-reservation authority.

## Durable Next Action Contract

Every processed inbound Chatwoot live-stock message must expose one durable SAM `next_action` on the decision packet:

- `answer_general_info`;
- `answer_location`;
- `answer_price`;
- `ask_one_missing_detail`;
- `prepare_draft_order`;
- `update_draft_order`;
- `prepare_quote`;
- `prepare_picture_response`;
- `no_reply_needed`;
- `escalate`.

Internal order-intake planner actions may still be preserved as implementation detail, but owner-facing review, learning, and handoff packets should use the durable SAM action. Customer send, quote send, reservation, payment, and stock movement remain owner/backend-gated.

## Supervision And Intervention Target

Live launch should be monitored through Chatwoot and the app dashboards. If SAM produces a risky draft, hostile conversation, pricing challenge, location challenge, or low-confidence result, the conversation should be owner-handoff.

The old n8n live-sales workflow had useful safeguards that remain required in the backend-native version:

- `conversation_mode` must support `AUTO` versus `HUMAN`;
- human escalation must carry enough context for the owner to reply safely;
- approved owner replies may be sent back to Chatwoot only through an explicit owner-approved send gate;
- Telegram escalation notifications should be cleaned up after resolution so the owner chat does not become noisy;
- stock tools may advise and match, but reservation/release remains a separate owner/backend gate.

The target escalation flow is:

1. SAM detects escalation reason.
2. Oom Sakkie/Telegram sends the owner a short summary and suggested response.
3. Owner approves, edits, or closes the escalation.
4. The response and resolution are logged.
5. The Telegram notification is deleted or marked resolved so the chat stays clean.

Until that full escalation rail is live, first public launch must remain closely supervised by the owner in Chatwoot.

## Controlled Launch Backend Surface

The backend-native controlled launch surface should expose:

- policy route for current env gates;
- inbound route for Chatwoot live-stock messages;
- conversation review/scoring packet;
- append-only conversation review event logging in `sam_live_stock_conversation_review_events`;
- escalation packet for Telegram/Oom Sakkie;
- owner-review Telegram packet for normal safe drafts, with customer message, SAM draft, risk score, and approve/edit/human/close actions;
- owner-approved send route, disabled unless the owner-send env gate is enabled;
- Telegram escalation send route, disabled unless the Telegram escalation send env gate is enabled;
- Telegram callback route for approve-send, edit-in-Chatwoot, close, keep-human, and resolved actions;
- resolved cleanup packet and delete route for deleting or marking the specific Telegram escalation notification;
- Chatwoot takeover payload and write route that sets `conversation_mode = HUMAN` without overwriting unrelated conversation attributes;
- advisory reservation plan route for matched candidates;
- owner-gated order-line reserve/release route that may operate only after an order exists with assigned `Pig_ID` lines.

These env gates must stay explicit:

- `SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED`
- `SAM_LIVE_STOCK_TELEGRAM_OWNER_REVIEW_SEND_ENABLED`
- `SAM_LIVE_STOCK_TELEGRAM_ESCALATION_SEND_ENABLED`
- `SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED`
- `SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED`
- `SAM_LIVE_STOCK_ORDER_RESERVATION_ENABLED`

Autoreply and LLM/Agent V3 remain disabled until live-stock reply quality has been tested in the owner's own chat and reviewed.

Reservation rule:

- Before draft order: SAM may recommend candidate pigs from `Purpose = Sale` availability only.
- Draft order: backend may create draft order only when facts, price, and stock gates pass.
- Reservation: owner/operator may reserve assigned order lines only through the explicit reservation gate.
- Release: owner/operator may release assigned order-line reservations through the explicit release action.
- SAM must never say an animal is held/reserved before the backend reservation action succeeds.

## Source References

- `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md`
- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md`
- `docs/09-vault-brain/03-business/LIVE_PIG_SALES.md`
- `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`
- `docs/09-vault-brain/08-business-rules/AMADEUS_FARM_PUBLIC_KNOWLEDGE.md`
- `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`
- `modules/sales/sam_sales_router.py`
