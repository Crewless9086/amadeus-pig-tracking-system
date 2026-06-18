# Agent Portfolio Review

Status: working business/advisor review as of 2026-06-18.

Purpose: summarize built agents, planned agents, useful future agents, sub-agent structure, automation level, and the money-first build order.

## Automation Levels

| Level | Meaning |
| --- | --- |
| 0 - Planned | Role is documented only. No runtime authority. |
| 1 - Read-only | Can summarize or recommend from existing data. No writes. |
| 2 - Draft/review | Can prepare drafts, packets, or recommendations. Owner approves before action. |
| 3 - Gated execution | Can write/send/post only through explicit backend gates, env flags, exact confirmations, and append-only audit events. |
| 4 - Rule-limited automation | Can act inside a pre-approved rule, budget, stock, customer, or safety boundary and escalate exceptions. |
| 5 - Exception-only autonomy | Normal cases run automatically; owner reviews only exceptions, failures, and strategy changes. |

The current system should not jump past Level 3 until real pilot results prove that the data, prompts, channel behavior, stock gates, and payment gates are reliable.

## Built Or Partly Built Agents

| Priority | Agent | Current status | One-line job | Current automation | Sub-agents / modules | Next needed build |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Sam Meat | Built for meat pilot | Customer-facing Chatwoot/WhatsApp meat intake agent that collects buyer facts and keeps conversation moving. | Level 3 for gated intake replies; Level 2/3 for approved follow-ups; no autonomous price/order/stock authority. | Sam Meat Intake, Sam Fact Extractor, Sam Chatwoot Hygiene, Sam Learning Evidence. Later split into Sam Meat, Sam Live, Sam Butcher/Custom Cuts. | Live pilot test after Render deploy; then reduce owner work in quote/order/document flow. |
| 2 | Butcher | Partly built | Matches meat customers to pigs/carcass halves and protects against overbooking. | Level 2 for recommendations; Level 3 for gated reservation actions from Farm App. | Match Engine, Carcass Assembly, Reservation Gate, Slaughter/Butcher Draft Builder. | Improve automatic prioritization of half-sold carcasses and operational exception rules. |
| 3 | Beacon / Prisma Marketing | Partly built | Creates demand through approved social/media campaigns and learns what produces real buyer leads. | Level 2/3: media library, campaign drafts, publish packets, manual evidence, performance packets, exact owner-confirmed Facebook text/image posting. No boost/spend/scheduling autonomy yet. | Strategy, Creative, Media Librarian, Scheduler, Performance Analyst. | Owner-approved image live smoke, then read-only Meta performance import. |
| 4 | Atlas / Analyst | Partly built | Learns from sales conversations and turns patterns into improvement proposals. | Level 1/2: append-only learning evidence and summaries only. No prompt/rule changes. | Sales Conversation Analyst now; later Farm Data Analyst, Campaign Analyst, Agent Quality Analyst. | Build regular learning summary and improvement proposal workflow. |
| 5 | Oom Sakkie | Built as command-center foundation | Owner-facing farm brain that summarizes state, routes tools, and keeps humans on the correct gate. | Level 1 mostly; some gated review surfaces. Does not replace Sam with customers. | Command Brief, Tool Router, Review Advisor, Specialist Dock. | Make the daily owner view simpler and turn agent outputs into one prioritized action list. |
| 6 | Ledger | Partly built/advisory | Business advisor for pricing, margin, pipeline value, follow-up priority, and money decisions. | Level 1/2 advisory. No customer sends, financial records, invoices, or price changes without gates. | Pricing Advisor, Pipeline Advisor, Margin Advisor, Follow-up Priority. | Add real margin/cost tables and sales pipeline value reporting. |
| 7 | Prism UI | Partly advisory, not a runtime agent | Reviews UI/UX and simplifies operator workflows. | Level 1/2 design review; implementation through normal code changes only. | Farm App UX, Mobile Operator UX, Oom Sakkie Command UX. | Continue focused simplification of Meat Leads and Beacon pages after sales pilot feedback. |

## Planned Core Agents

| Priority | Agent | One-line job | Recommended starting automation | Sub-agents / modules | Why it matters |
| --- | --- | --- | --- | --- | --- |
| 8 | Sam Live | Handles customer conversations for live pig sales. | Level 2 first, then Level 3 after stress tests. | Live Intake, Availability Checker, Quote/Order Handoff. | Live pig sales are already an operational stream and should reuse the Sam pattern once Meat Sales is proven. |
| 9 | Sam Butcher / Custom Cuts | Handles custom cut and butcher-specific customer conversations. | Level 2 first. | Custom Cut Intake, Cut Feasibility, Butcher Handoff. | Custom cuts can make money but create fulfilment complexity; keep separate from standard half/full carcass. |
| 10 | Herdmaster | Pig lifecycle, health, growth, weaning, breeding, and purpose recommendation specialist. | Level 1 first; Level 2 recommendations. | Litter Analyst, Growth Analyst, Health/Treatment Watcher, Purpose Recommender. | Good pig allocation decisions drive every future sale and reduce waste. |
| 11 | Admin / Finance Agent | Reads POPs, bank notifications, invoices, quotes, and expenses; reconciles money evidence. | Level 1/2 first; Level 3 for gated reconciliation events. | POP Reader, Bank Notification Reader, Invoice/Quote Clerk, Expense Classifier. | Biggest owner-work reducer after Sam: money proof, fake POP risk, and farm cost tracking. |
| 12 | Dispatch / Driver Agent | Plans delivery routes, driver views, customer updates, and delivery exceptions. | Level 2/3 gated updates. | Route Planner, Driver Mobile View, Journey Message Drafter. | Delivery experience and final-balance gate are critical to customer trust and cash safety. |
| 13 | Sentinel | Security, safety, exposed-route, secret, and unsafe-tool reviewer. | Level 1 only. | Route Reviewer, Secret Scanner, Tool Authority Auditor. | Needed before agents gain more automation, public posting, money, or physical controls. |
| 14 | Forge | Code and system health steward. | Level 1/2; code changes still through developer workflow. | Test Failure Reviewer, Migration Drift Checker, Docs Cleanup Reviewer. | Keeps the system from becoming messy and fragile as agent count grows. |
| 15 | Rootline | Crop, plant, irrigation, weather, and growing-condition specialist. | Level 1 first. | Irrigation Advisor, Weather Risk, Crop Task Planner. | Useful, but less money-immediate than meat sales unless crops become a near-term revenue stream. |

## Useful Additional Agents Later

| Priority | Agent | One-line job | Recommended starting automation | Notes |
| --- | --- | --- | --- | --- |
| 16 | Customer Success / Journey Agent | Keeps customers informed with story-led, non-spammy updates after booking. | Level 2/3 through approved journey sends. | May remain a Sam sub-agent instead of separate agent. |
| 17 | Compliance / Records Agent | Tracks veterinary, withdrawal, slaughter, food-safety, and audit documentation. | Level 1/2. | Important before scaling meat sales materially. |
| 18 | Procurement Agent | Tracks feed, butchery supplies, packaging, fuel, and service providers. | Level 1 first. | Supports margin accuracy and stock readiness. |
| 19 | Customer Memory / CRM Agent | Maintains buyer preferences, locations, order history, and follow-up timing. | Level 1/2. | Should be backend data, not a free-form memory blob. |
| 20 | Meta Ads Operator | Executes approved boosts and campaign budgets. | Level 2/3 only after Beacon performance import is trusted. | Could remain inside Beacon Scheduler/Performance Analyst. |

## Recommended Build Order To Make Money

1. **Finish the first Meat Sales live pilot loop.**
   - Sam receives inbound traffic.
   - Sam captures facts without owner chasing details.
   - Butcher recommends/reserves safely.
   - Deposit and final balance are confirmed from bank evidence.
   - Draft order/documents are created at the right stage.
   - Delivery/journey updates are controlled and useful.

2. **Finish Beacon's first real campaign loop.**
   - Upload, review, and approve real media.
   - Beacon posts one approved image campaign with exact owner confirmation.
   - Sam captures inbound leads from that campaign.
   - Beacon/Atlas compare campaign response against real qualified leads, not likes.

3. **Add the Finance/Admin evidence rail.**
   - POP received is not enough.
   - Bank-confirmed money unlocks operations.
   - Expense and cost tracking starts feeding Ledger margin advice.

4. **Tighten document generation.**
   - Quotes before commitment.
   - Draft invoices after accepted terms or order creation.
   - Final invoices after actual packed weight/final balance.
   - Sam can retrieve/send approved documents only through gated rules.

5. **Repeat the pattern for Live Pig Sales.**
   - Do not build all sales streams at once.
   - Use Sam Meat as the proven template: stress tests, Chatwoot hygiene, append-only facts, owner gates, then controlled sends.

## Current Go-Live Readiness

The system is close to a controlled private pilot, not yet broad public automation.

Ready enough:

- Backend-native Sam Meat is live-testable.
- Chatwoot inbound and hygiene rails exist.
- Meat lead/operator surface exists.
- Price book and estimate rules exist.
- Butcher match and carcass reservation gates exist.
- Deposit/final balance logic protects against fake POP.
- Beacon can prepare and owner-confirm public Facebook posts.
- Stress tests currently pass for Sam Meat with 0 known launch-blocking gaps.

Not ready enough:

- Real campaign image flow still needs one live smoke.
- Real customer pilot has not yet proven end-to-end conversion, payment, fulfilment, delivery, and final close.
- Quote/invoice/document timing is not fully productized for Sam.
- Finance/Admin bank-email/POP automation is not built.
- Meta performance import and boost execution are not yet trusted.
- Live pig and slaughter sales have not been migrated to the same backend-native agent pattern.

## Main Risks And Resolutions

| Risk | Why it matters | Resolution |
| --- | --- | --- |
| Owner still does too much manual review | The system will not scale if every normal lead becomes a maze. | Convert repeated owner decisions into rule tables and exception-only gates after pilot evidence. |
| Demand before fulfilment capacity | Beacon could create interest the farm cannot satisfy. | Beacon must read stock/carcass capacity and campaign caps before posting/boosting. |
| Fake POP / payment confusion | Releasing meat before bank confirmation loses money. | Keep POP as evidence only; build Finance/Admin bank confirmation rail next. |
| Wrong price or weight promise | Meat final amount depends on actual packed weight. | Keep estimates explicit; final quote/invoice must use actual packed weight when known. |
| Half-carcass waiting state | One buyer can be ready while the carcass is not fully committed. | Butcher prioritizes matching the second half and Sam keeps customer warm without overpromising. |
| Too many agents too early | More names can create confusion instead of automation. | Build sub-agents as backend modules first; only promote to named agents when the workflow is proven. |
| Chatwoot source attribution weak | Beacon cannot optimize without knowing which post created which buyer. | Add campaign/source attribution to Sam lead capture and Chatwoot attributes. |
| UI overload | Owner avoids the tool if it feels harder than doing it manually. | Keep adding one-screen operator summaries and next-click flows; hide audit detail behind drill-ins. |
| Public posting mistakes | Wrong copy/media can damage trust. | Keep exact owner confirmation until approved campaign rules are proven. |
| Missing cost/margin truth | Sales can look good while losing money. | Build cost tables for slaughter, butchery, packaging, fuel, feed, labour, and delivery. |

## Questions For Owner

1. What is the first live pilot cap: how many half/full carcass buyers should Beacon/Sam accept before the campaign pauses?
2. Should first campaign traffic go to Facebook page post only, WhatsApp status, or both?
3. What quote/invoice timing do you want: quote before deposit, invoice after deposit, or invoice only after actual packed weight?
4. Which bank notification source should the Finance/Admin agent read first: email, bank export, manual upload, or Chatwoot POP attachments?
5. Who is the first driver user for `/sales/meat-driver`, and should that be login-based or magic-link based later?
6. For first pilot delivery, do we deliver only Riversdale/nearby, or do we allow collection as the default?
7. What is the minimum acceptable margin per carcass after slaughter, butchery, packaging, and delivery costs?

## Owner Pilot Answers - 2026-06-18

- Available supply: there are pigs very close to 60kg over the next few weeks.
- First campaign channel: Facebook only.
- Quote/invoice timing: owner is open to recommendation because meat final amount depends on actual packed weight. Recommended model: estimated quote before deposit, deposit request against estimate, final tax/commercial invoice after actual packed weight and final amount are known.
- Finance/Admin source direction: eventually all relevant sources. Start with email access/filtering, then route bank notifications, POP attachments, invoices, quotes, and human-review exceptions into the correct agent rail.
- First delivery zone: Riversdale and nearby towns first: Mossel Bay, Riversdale, Albertinia, Still Bay. George can be added later.
- Minimum margin: not set yet. First pilot should capture all costs so Ledger can calculate real margin per carcass.

## Immediate Recommendation

Do not build a new large agent yet. The next money-first sequence should be:

1. Beacon approved-image live smoke.
2. One real controlled Meat Sales campaign.
3. Sam end-to-end lead test from campaign source to draft order.
4. Finance/Admin payment evidence rail.
5. Quote/invoice/document gate.
6. Then repeat the proven Sam pattern for live pig sales.
