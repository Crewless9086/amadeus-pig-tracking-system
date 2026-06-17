# Meat Sales Launch Plan

## Status

Active money-first plan as of 2026-06-17.

The goal is to get the meat-sales system into a controlled pilot where it can generate real demand, handle Chatwoot conversations cleanly, create usable leads, support owner review, and learn from every sales conversation.

## Current System Position

Meat Sales is backend-native enough for private pilot testing:

- Sam Meat receives Chatwoot inbound webhook messages through the backend.
- Sam captures meat preorder facts, delivery details, payment preference, and customer context.
- Farm App `/sales/meat-leads` is the operator surface.
- Price book, estimate rules, Butcher pig matching, carcass reservation, deposit gate, instruction drafts, fulfilment timeline, driver route, journey drafts, packed-weight reconciliation, final balance, and delivery release gates exist.
- Chatwoot sales hygiene is implemented behind `SAM_MEAT_CHATWOOT_HYGIENE_ENABLED=1`: Sam Meat writes meat labels and custom attributes while preserving existing Chatwoot labels and order attributes.
- The Sam Meat sales stress-test pack covers 40 realistic buyer scenarios and passes launch-blocking assertions. Report: `MEAT_SALES_STRESS_TEST_REPORT.md`.
- Sam Meat now captures buyer budget amount, target packed kg, and match preference for later Butcher matching.
- Customer sends and third-party informs remain gated by env flags and exact approval where required.

This is not yet a public money machine. Beacon now has a draft-only launch packet ready for owner review; the next work should add the conversation learning loop before real traffic is pushed into it.

## Business Priority

Start with Meat Sales because it has the clearest near-term profit path.

Do not forget the other sales streams:

- Live pig sales remain the existing operational sales stream.
- Slaughter/abattoir sales remain the fallback outlet for pigs that do not sell through meat at the right time.
- Assisted slaughter is a later add-on offer.
- Custom cuts are later, once standard half/full carcass sales are stable.

Near-term money test:

1. Make the Chatwoot inbox visually clean.
2. Stress-test Sam with messy real buyer behavior.
3. Use Prisma/Beacon to create owner-approved public demand drafts.
4. Route inbound interest into Sam and the Farm App.
5. Review what people ask, where they get stuck, and what converts.

## Roles

| Role | Near-term job | Must not do yet |
| --- | --- | --- |
| Sam | Customer conversation and intake in Chatwoot. Collect product, cut set, town, delivery/collection, timing, payment method, address/location, POP evidence, and customer confirmation. | Invent stock, price, timing, bank confirmation, or final booking. |
| Butcher | Match customer needs to pigs/carcass halves, prioritize open half-carcass reservations, protect against overbooking. | Slaughter/book/allocate without approved gates. |
| Ledger | Business advisor for pricing, conversion, pipeline value, margin, and follow-up priority. | Send messages, change prices, or create financial records without gates. |
| Prisma/Beacon | Marketing and public demand-generation drafts for social media, WhatsApp status/channel, Facebook, Instagram, and story-led launch copy. | Post publicly or message customers without owner approval. |
| Atlas / Analyst | Conversation learning, demand patterns, objections, confusion, and improvement recommendations. | Rewrite prompts or system behavior automatically. |
| Oom Sakkie | Owner command center. Summarize what matters and hold the system together. | Become a second uncontrolled customer-facing agent. |

Naming note: existing docs use `Beacon` for public/social content and `Prism` for UI/design. The owner sometimes says `Prisma` for the marketing/social role. Until renamed deliberately, treat `Prisma/Beacon` as the marketing demand-generation role.

Full Beacon scope note: Beacon's long-term role is larger than the Phase 11N launch packet. The future media library, sale-readiness scanning, campaign planning, scheduling, paid promotion, monitoring, and optimization scope is logged in `docs/05-ai/agents/beacon/BEACON_SCOPE.md`. Those automation phases are parked until the sales learning loop and approval rules are proven.

## Next Build Sequence

### 1. Chatwoot Sales Hygiene

Goal: make the inbox easy to understand at a glance.

Status: complete in Phase 11L.

Implemented outcome:

- Define meat-sales labels and custom attributes.
- Backend Sam Meat applies safe labels/attributes when it creates or updates a meat lead.
- Labels must append/preserve existing labels, not wipe them.
- Attributes must preserve existing order conversation fields where relevant.
- Farm App and Chatwoot should agree on visible state.
- The backend fetches the current conversation first, merges attributes, and unions labels before writing to Chatwoot.
- Enable with `SAM_MEAT_CHATWOOT_HYGIENE_ENABLED=1` plus the existing Chatwoot API envs.

Useful labels:

- `meat_lead`
- `half_carcass`
- `full_carcass`
- `set_a`
- `delivery`
- `collection`
- `deposit_pending`
- `pop_received_unverified`
- `deposit_confirmed`
- `balance_due`
- `ready_for_delivery`
- `needs_followup`
- `lost_lead`
- `test_flow`

Useful custom attributes:

- `sales_lane`
- `meat_product_type`
- `meat_cut_set`
- `meat_delivery_mode`
- `meat_delivery_town`
- `meat_lead_id`
- `meat_order_id`
- `meat_payment_state`
- `meat_next_gate`
- `meat_followup_due_at`
- `meat_last_customer_intent`

### 2. Sales Stress-Test Pack

Goal: find failure points before public launch.

Status: complete in Phase 11M.

Implemented outcome:

- 30-50 realistic test conversations.
- Include vague buyers, budget buyers, price objections, delivery questions, location pins, POP messages, wrong product, live-pig confusion, cut-set questions, slow replies, closed WhatsApp windows, and angry/confused messages.
- Each scenario should define expected facts, expected next question, expected labels/attributes, and what must not happen.
- 40 scenarios are implemented in `modules/sales/sam_meat_stress.py`.
- The local runner is `scripts/sam_meat_stress_test.py`.
- The latest run passed 40/40 launch-blocking assertions with 6 known improvement opportunities.

Structured preference capture completed after first stress run:

- Budget amount is now a structured Sam/Butcher matching fact.
- Target packed kg is now a structured Sam/Butcher matching fact.
- Match preference such as heaviest, soonest, cheapest, or best fit is now structured.

Remaining useful improvements:

- Plain-text Google Maps links, Afrikaans/typos, frustration wording, and non-pork redirects should improve after the preference capture slice.

### 3. Prisma/Beacon Meat Launch Campaign

Goal: create demand without overpromising.

Status: complete in Phase 11N.

Implemented outcome:

- Owner-review-ready campaign angles for the first pork freezer pilot.
- Draft social captions, WhatsApp status/channel text, Facebook/Instagram post copy, and short story updates.
- Every draft must state that availability is limited and orders are pre-booked.
- No post/send automation until owner approval and channel rules are explicit.
- `modules/sales/beacon_campaign.py` builds the canonical draft-only launch packet.
- `docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md` contains the owner-review copy packet.
- `docs/05-ai/agents/beacon/BEACON_SCOPE.md` logs the full future Beacon vision so it can be built later in controlled phases.
- Tests prove Beacon has no authority to post publicly, send customer messages, call Chatwoot/Meta/n8n, create orders, create quotes/invoices, reserve carcasses, change stock, book slaughter/butchery, or confirm payment.

Owner review before using the copy:

- Choose first channel: WhatsApp status, WhatsApp channel, Facebook, Instagram, or direct known buyers.
- Choose approved photo/video assets.
- Confirm whether public copy should mention price/kg or keep price on request.
- Confirm first pilot demand cap before Sam keeps collecting more buyer interest.

### 4. Conversation Learning Loop

Goal: make every sales conversation improve the system.

Required outcome:

- Append-only learning events from sales conversations.
- Track customer wanted, missing facts, objections, confusion, Sam misses, conversion/loss reason, and improvement suggestion.
- Analyst/Atlas summarizes patterns for Oom Sakkie.
- Human approval remains required before prompt/rule/tool changes.

### 5. Other Sales Streams

Goal: keep the larger sales system honest.

Required outcome:

- Live pig sales stay operational and stable.
- Slaughter/abattoir sales get cleaner value/payment tracking later.
- Assisted slaughter and butcher-specific sales are planned after standard meat orders are proven.
- Do not build every sales stream at once; use Meat Sales to prove the agent pattern first.

## Documentation Cleanup Policy

Keep:

- Full business context in `PORK_SALES_MODEL.md`.
- Active build order in `NEXT_STEPS.md`.
- Current live status in `CURRENT_STATE.md`.
- Chatwoot label/attribute rules in `docs/04-n8n/CHATWOOT_ATTRIBUTES.md`.
- Agent role boundaries in `docs/05-ai/AGENT_ROLES.md` and `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`.

Do not keep duplicate scratch plans. If a note matters, move it into one of the files above and remove it from `planning/ToDoList.md`.
