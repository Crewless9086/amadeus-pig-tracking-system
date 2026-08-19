# SAM Live Stock Sales Workflow

Status: Current authority. SAM Live Stock may create backend draft orders when source truth, fact completeness, availability, and pricing gates pass. It does not reserve stock, confirm payment, send quotes, or make final customer promises without the relevant backend/owner gates.

## Purpose

SAM Live Stock Sales turns customer interest in live pigs into clean, source-backed sales opportunities. The workflow must reduce feed-pressure losses without creating wrong stock promises or confusing live-stock sales with meat sales.

## Lane Boundary

The general-conversation doctrine governs first. SAM must classify and graduate
to a specialist lane before making specialist claims, calling specialist tools,
or preparing or performing consequential actions. It need not classify a lane
before an ordinary conversational reply:

- `meat_sales`: pork, carcass, cut sets, freezer packs, chops, roasts, mince, ribs, belly, delivery of meat;
- `live_stock_sales`: live pigs, piglets, weaners, growers, finishers, gilts, boars, sows, pigs to raise, pigs to buy alive;
- `slaughter_abattoir_sales`: assisted slaughter, abattoir, slaughter pig, kill/cut service, slaughter booking, ready-for-slaughter handoff;
- `farm_general_question`: general farm/product questions without buying intent;
- `owner_handoff`: complaint, dispute, special pricing, payment proof, refund, breeding exception, or customer asks for Charl/owner;
- `unclear`: mixed, vague, contradictory, or low-confidence intent.

Mixed meat/live-stock language must clarify before proceeding. Example: `I want pork and maybe two weaners` is not safe for a single lane.

`unclear` remains a valid discovery state and does not by itself require
Telegram escalation or HUMAN ownership.

## Operating Flow

1. Customer message arrives through Chatwoot/WhatsApp, manual owner capture, or a future campaign source.
2. General SAM responds or clarifies naturally until specialist graduation is
   required.
3. SAM Sales Router classifies the lane before live-stock claims, tools, order
   preparation, or other consequential work. If the lane is not
   `live_stock_sales`, continue general discovery or use the correct specialist.
4. If lane is live stock, collect only facts the customer has not supplied.
   When both size and sex are missing, ask both together using plain-language
   size/weight choices. Never require the customer to know internal categories.
5. Load existing conversation/order-intake memory when the backend runtime exists.
6. Read current availability from backend source truth.
7. Prepare advisory next action, owner packet, or safe draft reply.
8. If the customer request and active pricing are present, SAM may prepare a requested-items draft quote with truthful partial or `Unavailable` recommendations. Creating or updating a canonical draft order remains a separate backend action and must not attach, allocate or reserve a pig.
9. Backend/owner gates decide whether reservation, quote, customer send, or payment-dependent actions may happen.
10. Append learning evidence after blocked, unclear, rejected, or corrected outcomes.
11. If the customer becomes hostile, repeatedly demands the exact farm location, calls the farm a scam, or aggressively challenges pricing, SAM should close politely, stop replying, and escalate/log the conversation for owner visibility.

## Qualification Evidence

- Blank, `Any`, `Unknown`, defaulted, or inferred persisted values are not
  evidence that the customer supplied a preference.
- An explicit customer statement such as `either` or `no preference` is valid
  sex-preference evidence because it is independently present in chronology.
- Current customer chronology overrides a conflicting intake projection.
- A category-derived weight default must not satisfy a requested weight/size
  field.
- Missing stock or price evidence blocks only the unsupported stock or price
  claim. It does not block a safe size/sex clarification or supported product
  explanation.
- A concise customer qualification answer stays in the Livestock lane so the
  durable intake can advance; it must not fall back to general conversation.

## Complete Sales Inbox Operation

The configured Chatwoot inbox, read with complete deterministic pagination, is
the source inventory. Every current Livestock sales conversation receives one
durable disposition: Level 1 reply now, awaiting customer, owner-review draft,
exact fact required, closed provider window, protected decision, technical
evidence defect, handled, or retired. Open status alone never creates owner
work. Already answered, duplicate, spam, acknowledgement-only, stale, and
non-sales conversations remain audit evidence but leave the actionable queue.
`can_reply=false` must be expanded into its exact provider/evidence reason.

Inventory and chronology reads are bounded and conversation-isolated. A failed
later inventory page may yield explicit partial coverage only for conversations
whose exact row and complete chronology were loaded. One unavailable history
quarantines that conversation. First-page loss, duplicate identities,
account/inbox conflict, changed chronology or systemic binding failure stops the
cohort. Before claim, revalidate chronology and claim state. After an exception,
fresh claim-ledger evidence must prove `not_crossed`; `crossed` or
`indeterminate` boundaries prohibit automatic retry.

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
- Existing `draft_order_id` must be reused and line-synced; repeated qualified conversation turns must not create duplicate draft orders.
- No automatic stock reservation.
- No customer may be told a pig is held unless backend reservation succeeds.
- Price source is `public.sales_pricing`, inherited from `SALES_PRICING`, edited through `/sales/sam-pricing`, and resolved by effective date.
- No payment is confirmed from POP alone.
- No breeding candidate, sow, boar, or replacement-quality gilt may be offered through the normal live-stock sale lane.
- Only source-truth `Purpose = Sale` pigs may be offered.
- No sold, dead, exited, reserved, terminal, off-farm, source-conflicted or explicitly health-, welfare-, quarantine-, movement- or sale-held animal may be recommended. A recorded food-chain withdrawal is a compact disclosure and slaughter/food-chain blocker, not by itself a live-sale blocker.
- Missing or stale weight lowers confidence and may request a fresh weight; it does not prevent the requested-items draft quote or require a specific pig.
- No old n8n or Google Sheet value may override app/Supabase truth.
- Do not share the exact farm location. Live-stock handover is Riversdale or Albertinia after the order path is confirmed.
- Do not argue about scam accusations, exact location, or pricing. Close politely and escalate/log when the buyer is rude, aggressive, or already negative.
- Do not send repeated closing replies after the customer has naturally ended the conversation.

## Customer-Requested Delivery Option

Collection remains the default and SAM must not introduce delivery as an open offer. If the customer explicitly asks about delivery, transport, or drop-off, the backend may prepare an advisory option using R20.00 per one-way kilometre. The packet exposes destination, distance source/status, rate/fee source, eligibility, and owner override audit fields. It stops at owner review: no automatic customer/quote send, reservation, payment, or order/stock write is permitted.

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

## Outbound Delivery Truth

Delivery containment is conversation-scoped. A provider failure or ambiguous
outcome preserves the exact append-only attempt and creates a delivery
exception with no retry; unrelated exact Level 1 bindings may continue.
A systemic provider outage, corrupted claim rail, cross-binding identity or
chronology collision, or authority breach stops the complete cohort.
Chatwoot acceptance alone never counts as provider-confirmed delivery.

## Isolated Always-On Level 1

GateKeeper and the existing backend inbound route remain the single event
path. The append-only Livestock control event supplies the policy state,
activation cutoff, exact carried follow-ups, expiry, owner principal, and kill
state without changing shared Render environment keys. Each inbound is
independently reclassified against current chronology, the provider window,
ordinary Livestock intent, evidence-backed claims, and the durable
claim-before-send rail.

Safe qualification and intake progression may continue when a count or price
is unavailable, provided the reply omits that unsupported claim. Binding
quotes, negotiated terms, delivery promises, reservations, allocations,
orders, payments, ownership, and farm or animal writes remain prohibited.

For ordinary pig enquiries, SAM explains relevant choices in customer
language: small piglets are approximately 2–6 kg, weaned piglets 7–19 kg,
growing pigs 20–49 kg, larger pigs 50–79 kg, and slaughter-size pigs 80 kg and
above. Internal categories may supplement but never replace that explanation.
Supported Riversdale/Western Cape or collection-process guidance must answer a
direct location or handover question. Unknown availability or price is
explicitly qualified and omitted; it does not justify withholding another
supported answer.

The pre-send usefulness gate rejects pure deferrals, vague questions where
specific choices exist, repeated questions, omitted supported direct answers,
unsupported commercial claims, and replies that claim progress without a
useful next step. Wording may vary naturally when semantic coverage,
provenance and authority remain equivalent.
Provider ambiguity quarantines only the exact attempt and never retries.
Systemic provider, identity, claim-rail, isolation, or authority failure
requires an append-only killed control event.

All normal, owner-approved, Telegram-assisted, and future automatic replies use
the shared
[`OUTBOUND_DELIVERY_TRUTH_STANDARD.md`](../07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md).
HTTP 2xx or Chatwoot `status=sent` means accepted-unverified until an exact
provider delivered/read event exists. Accepted or ambiguous outcomes are not
automatically retried. Owner-card cleanup cannot claim customer completion.

## Supervision And Intervention Target

Live launch should be monitored through Chatwoot and the app dashboards. If SAM produces a risky draft, hostile conversation, pricing challenge, location challenge, or low-confidence result, the conversation should be owner-handoff.

The old n8n live-sales workflow had useful safeguards that remain required in the backend-native version:

- conversation ownership must support `AUTO_GENERAL`, `AUTO_SPECIALIST`, and
  `HUMAN`, independently from business lane;
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

## Media Intake Backlog

Current SAM Live Stock runtime is text-first. Voice notes, customer photos, screenshots, and emoji-only messages must not be treated as understood sales facts until a media intake layer exists.

Required future mission:

- download approved Chatwoot media attachments through backend-authenticated rails;
- transcribe voice notes before routing;
- classify photos/screenshots without exposing private media publicly;
- attach transcript/media summary to the decision packet;
- keep customer sends, quote sends, reservations, payments, and stock movement owner-gated;
- add tests for Afrikaans voice notes, unclear photos, emoji-only replies, and media privacy.

Until then, media-only messages should be owner-visible and may trigger a practical clarification, but they must not create orders, reserve pigs, quote, or promise stock.

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

- `docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md`
- `docs/09-vault-brain/07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md`
- `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`
- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md`
- `docs/09-vault-brain/03-business/LIVE_PIG_SALES.md`
- `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`
- `docs/09-vault-brain/08-business-rules/AMADEUS_FARM_PUBLIC_KNOWLEDGE.md`
- `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`
- `modules/sales/sam_sales_router.py`
