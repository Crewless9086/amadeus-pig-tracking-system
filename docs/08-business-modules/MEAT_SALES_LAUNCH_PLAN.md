# Meat Sales Launch Plan

## Status

Active money-first plan as of 2026-06-18.

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
- Beacon now has private media-library metadata/API foundation, a Farm App review UI, approved-media campaign draft selection, and owner-review publish packet preparation for future approved photo/video use.
- Customer sends and third-party informs remain gated by env flags and exact approval where required.

This is not yet a public money machine. Beacon now has a draft-only launch packet, conversation learning evidence, a safe private media-library foundation, a Farm App media review UI, approved-media draft pairing, and publish packet preparation. The next work should define a manual public posting execution checklist and evidence capture before real campaign traffic is pushed into it.

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

Full Beacon scope note: Beacon's long-term role is larger than the Phase 11N launch packet. The future media library, sale-readiness scanning, campaign planning, scheduling, paid promotion, monitoring, and optimization scope is logged in `docs/05-ai/agents/beacon/BEACON_SCOPE.md`. Phase 11P created the private media-library foundation only; posting, scheduling, spend, and automatic public media use remain parked until approval rules are proven.

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

Status: complete in Phase 11O.

Implemented outcome:

- Append-only learning events from sales conversations.
- Track customer wanted, missing facts, objections, confusion, Sam misses, conversion/loss reason, and improvement suggestion.
- Analyst/Atlas summarizes patterns for Oom Sakkie.
- Human approval remains required before prompt/rule/tool changes.
- `supabase/migrations/202606180001_create_meat_sales_conversation_learning_events.sql` creates the append-only learning event rail.
- `modules/sales/conversation_learning.py` builds deterministic learning evidence from Sam Meat inbound handling.
- Sam Meat attempts to record learning evidence after processing inbound messages, without blocking the lead/reply path if learning storage is unavailable.
- Farm App APIs expose `GET /api/sales/meat-learning` and `GET/POST /api/sales/meat-leads/<lead_id>/learning-events`.
- Oom Sakkie has a read-only `sales_conversation_learning_status` tool for summary patterns.
- Learning records explicitly set `applies_learning_now = false` and cannot change prompts, runtime, workflows, customer messages, public posts, quotes, orders, reservations, stock, dispatch, or physical actions.

### 5. Beacon Media Library Foundation

Goal: keep campaign media organized without giving Beacon premature public authority.

Status: complete in Phase 11P.

Implemented outcome:

- Private Supabase Storage decision: raw intake bucket `beacon-raw-intake`, approved-media bucket `beacon-approved-media`.
- Append-only media asset metadata and event history for source, tags, sale-stream relevance, quality, privacy/safety, owner approval, and campaign usage.
- Backend APIs expose policy, list/register, small-file upload, and asset event recording under `/api/sales/beacon/*`.
- Standard upload is capped at 6MB until a later resumable/TUS upload build exists.
- `docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md` records the bucket, env, upload, and authority rules.
- No Meta, public posting, scheduling, paid spend, customer messaging, quote, invoice, order, stock, reservation, dispatch, prompt/runtime, or automatic media-use authority is added.

Next gate:

- Completed live: private Supabase buckets exist, envs are configured, and one small Render upload/readback smoke passed.
- Build the Farm App Beacon Media Review UI before public-use or scheduling automation.

### 6. Farm App Beacon Media Review UI

Goal: let the owner review campaign assets without leaving the operational Farm App.

Status: complete in Phase 11Q.

Implemented outcome:

- `/sales/beacon-media` lists Beacon media assets from the backend.
- Filters support needs review, approved, rejected, archived, and media type.
- Farm App can upload a small file into the private raw-intake bucket for review.
- Owner actions record append-only review events: note, approve public use, reject, archive.
- Effective review status is derived from latest append-only event so filters work without mutating original asset rows.
- Public posting, scheduling, paid spend, customer messages, quotes, invoices, orders, stock, reservation, dispatch, and automatic public media use remain locked.

Next gate:

- Deploy and owner-check `/sales/beacon-media`.
- Phase 11R should connect approved media to Beacon campaign draft selection while public posting remains manual/owner-approved.

### 7. Beacon Approved-Media Campaign Draft Selection

Goal: let Beacon recommend which approved asset fits each draft without posting.

Status: complete in Phase 11R.

Implemented outcome:

- `GET /api/beacon/campaign-draft-selection` builds a review-only draft/media pairing packet.
- Only assets with effective approval status `approved` are eligible.
- Farm App `/sales/beacon-media` shows draft/channel pairings, recommended asset, and reason.
- If no approved assets exist, the draft remains text-only and the UI says no owner-approved media is available.
- Public posting, scheduling, paid spend, customer messages, signed public URLs, quotes, invoices, orders, stock, reservation, dispatch, and automatic public media use remain locked.

Next gate:

- Deploy and owner-check `/sales/beacon-media`.
- Phase 11S should define the owner-approved campaign publish packet/approval rail. Keep posting manual or exact-owner-approved until public-send rails are proven.

### 8. Beacon Campaign Publish Packet Review

Goal: prepare exact public-post review packets without posting.

Status: complete in Phase 11S.

Implemented outcome:

- `POST /api/beacon/campaign-publish-packet` builds an owner-review-only packet.
- Packet binds exact draft copy, selected channel, optional approved media asset, pilot cap, and owner notes.
- Selected media is validated against approved Beacon media only.
- Farm App `/sales/beacon-media` has a Publish Packet panel.
- Safety checks confirm limited preorder wording, no forbidden promise, approved media, no public send/post, no Meta call, and no signed URL creation.
- The packet does not persist approval, post publicly, schedule, spend, send customer messages, call Meta, create signed URLs, create quotes/invoices/orders, change stock, reserve carcasses, dispatch, or change prompts/runtime.

Next gate:

- Deploy and owner-check `/sales/beacon-media`.
- Phase 11T should define manual public posting execution checklist and evidence capture before direct platform automation.

### 9. Beacon Manual Public Post Evidence

Goal: capture evidence after the owner manually posts a Beacon packet publicly.

Status: complete in Phase 11T.

Implemented outcome:

- `supabase/migrations/202606180003_create_beacon_manual_post_events.sql` creates append-only manual post evidence.
- `GET /api/beacon/manual-post-evidence` lists recent evidence.
- `POST /api/beacon/manual-post-evidence` records a manual post evidence event.
- Farm App `/sales/beacon-media` has a Manual Post Evidence panel below Publish Packet.
- Evidence can include publish packet ID, channel, post URL/evidence, posted time, posted by, campaign label, notes, and initial manual metrics.
- This does not post, schedule, boost, spend, call Meta, call Chatwoot/n8n, send customer messages, create quotes/invoices/orders, change stock, reserve carcasses, dispatch, or change prompts/runtime.

Next gate:

- Phase 11U should add performance tracking and boost recommendations.
- Beacon can recommend whether a Facebook post should be boosted only after manual evidence exists. Direct Meta Ads automation remains a later reviewed build with explicit owner spend caps and credentials.

### 10. Beacon Performance Tracking And Boost Recommendation Packet

Goal: track campaign performance and prepare owner-review boost recommendations without spending money.

Status: complete in Phase 11U.

Implemented outcome:

- `supabase/migrations/202606180004_create_beacon_campaign_performance_events.sql` creates append-only performance evidence.
- `GET /api/beacon/campaign-performance` lists performance events.
- `POST /api/beacon/campaign-performance` records a performance event and returns a boost recommendation packet.
- Farm App `/sales/beacon-media` has a Performance + Boost Recommendation panel.
- Recommendations can be `light_boost_owner_review`, `do_not_boost`, `wait_for_more_data`, or `owner_review_required`.
- Recommended spend is capped at R500.
- The primary optimization signals are messages to Sam and qualified buyer leads, not likes.
- This does not call Meta, boost, spend, schedule, send customer messages, create quotes/invoices/orders, change stock, reserve carcasses, dispatch, or change prompts/runtime.

Next gate:

- Phase 11V should design read-only Facebook/Meta performance import.
- Actual paid boost execution remains a later reviewed build with owner-approved spend caps and Meta credentials.

### 11. Beacon Owner-Approved Facebook Page Post Gate

Goal: let Beacon publish an exact owner-reviewed Facebook Page text post for the live pilot.

Status: complete in Phase 11V, pending deploy/env/live smoke.

Implemented outcome:

- `supabase/migrations/202606180005_create_beacon_facebook_post_execution_events.sql` creates append-only Facebook post execution evidence.
- `GET /api/beacon/facebook-posting-policy` reports whether live Facebook posting is armed.
- `GET /api/beacon/facebook-post-executions` lists post execution evidence.
- `POST /api/beacon/facebook-post-executions` posts exact text to the configured Facebook Page only when all gates pass.
- Farm App `/sales/beacon-media` has a Facebook Page Post panel.
- Owner must type `POST EXACT BEACON PACKET` before execution.
- Disabled, misconfigured, failed, and successful attempts are recorded.

Required envs:

- `BEACON_FACEBOOK_POSTING_ENABLED=1`
- `BEACON_FACEBOOK_PAGE_ID`
- `BEACON_FACEBOOK_PAGE_ACCESS_TOKEN`
- Optional: `BEACON_FACEBOOK_GRAPH_VERSION`

Boundary:

- This posts text-only to the Facebook Page feed.
- It does not boost, spend, schedule, DM customers, create orders/quotes/invoices, change stock, reserve carcasses, or change runtime/prompts.
- Automatic media posting remains later because private Beacon media needs a safe public upload/URL strategy.

Next gate:

- Deploy and live-smoke one post.
- Then build read-only Meta/Facebook performance import.

### 12. Other Sales Streams

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
