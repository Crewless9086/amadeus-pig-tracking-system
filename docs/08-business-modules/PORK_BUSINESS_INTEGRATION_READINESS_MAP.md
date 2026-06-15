# Pork Business Integration Readiness Map

## Status

Phase 11A planning bridge.

This is not a full meat-sales implementation backlog yet. It defines how the existing farm system should connect before new pork/meat workflows are built.

## Purpose

The pork business module must improve business decisions, not create disconnected screens.

This map connects:

- litter and weaning outcomes
- pig growth and weights
- pig purpose/allocation
- livestock sales
- slaughter/abattoir sales
- future meat orders
- revenue and margin reporting
- backend-owned lifecycle actions

The first implementation should be read-only and decision-useful. Write actions should only be added once the farm process is clear enough to test in real use.

## Operating Principle

One pig should have one operational truth.

The system should not require duplicate manual updates across litter, pig, sales, slaughter, and reporting pages. A backend-owned action should update the correct source record once, and other pages should read from that truth.

The allocation model should be dynamic, not a fixed one-time label. A pig can move through a planning funnel as new weights, growth rates, orders, and business outlets change.

Owner direction 2026-06-04:

- Purpose should be suggested after weaning from wean weight, average daily gain, and litter/parent quality.
- Fast growers from good litters are the most valuable animals: first review as breeding candidates, then meat candidates, then slaughter/abattoir if not sold through the meat path in time.
- Current grow-out animals mostly go to slaughter/abattoir because that is the available higher-income outlet until the meat product business is live.
- Future meat animals should be young and weight-dependent. If they sit past the meat weight/window without a confirmed meat sale, they should fall back to slaughter/abattoir rather than being held too long.
- Slow growers or underperforming pigs should be considered for livestock sale to reduce feed cost and free capacity.
- Older breeding females should move toward slaughter/abattoir decisions based on age, condition, weight, and breeding usefulness.
- Unknown purpose should remain a data/classification problem. If the system cannot support a suggested purpose from data, the pig should stay in `Needs Data` or `Needs Classification`, not silently become a sale/meat/slaughter candidate.

## Current Working Sources

| Area | Current source | Useful today | Gap before business-module writes |
| --- | --- | --- | --- |
| Pig identity and state | `PIG_MASTER` | Pig ID, tag, type, sex, status, on-farm state, pen, purpose, litter, parent links, exit fields, carcass weight | Purpose/allocation is still mostly manual or unknown. |
| Litter outcomes | `LITTERS`, `LITTER_OVERVIEW`, linked `PIG_MASTER` rows | Birth counts, live piglet rows, weaning state, survival, attention actions | Historical reconciliation and later lifecycle event log remain open. |
| Weaning | Backend `mark_litter_weaned` action | Updates litter and linked piglet weaning fields | Does not yet classify future purpose. |
| Weights | `WEIGHT_LOG`, weight report, bulk weights page | Latest weight, growth report, loss flags, printable/bulk capture path | Bulk weights still awaits real farm live test; edit/void audit is deferred. |
| Breeding analytics | `MATING_OVERVIEW`, `LITTER_OVERVIEW` | Sow/boar performance and drill-in context | Suggestions should wait for more real data and owner trust. |
| Livestock sales | Current order flow and `ORDER_LINES` | Customer order, reservation, completion, pig exit for live sale | Later Supabase transaction linkage should be planned, not patched. |
| Slaughter sales | Supabase `sales_transactions`, `sales_transaction_items` | Slaughter batches, buyer/destination, amounts, payment state, linked pigs | Pig exit confirmation is explicit and still tied to Google Sheets `PIG_MASTER`. |
| Dashboard/reporting | Dashboard summaries and `/sales-dashboard` | Sales streams, monthly values, outcome counts, drill-ins | Future margin/profit reporting needs cost/yield inputs. |
| Pork/meat model | `PORK_SALES_MODEL.md` | Pricing, target weights, cut sets, deposit rules, weekly rhythm | Needs translation into data contracts and staged UI. |

## Allocation States

The first useful business-module read model should classify active/on-farm pigs into practical planning buckets. These are advisory labels, not automatic writes.

| Readiness bucket | Meaning | Likely inputs |
| --- | --- | --- |
| Needs Data | Not enough data to make a useful business decision. | Missing tag, sex, weight, purpose, age/stage, or current pen. |
| Needs Classification | The pig has enough basic identity data but still needs a purpose decision. | Weaned pig with tag/sex/weight but `Purpose = Unknown`; evaluate wean weight, growth, litter quality, and current outlet demand. |
| Growing | Pig is active/on farm but not near any sale/slaughter/meat threshold. | Active status, on farm, latest weight below target, no sale allocation. |
| Livestock Candidate | Pig may be suitable for live sale. | Active/on farm, suitable purpose/stage, sale-ready weight band, not already reserved/sold/slaughter-linked. |
| Slaughter Candidate | Pig may be suitable for abattoir/intermediate slaughter sale. | Active/on farm, around slaughter target or heavier, not reserved, not linked to another active sale. |
| Meat Candidate | Pig may be suitable for future pre-sold carcass/half-carcass order. | Active/on farm, around 60 kg target, good health/growth data, not allocated elsewhere. |
| Retain / Breeding Candidate | Pig may be worth keeping for breeding. | Purpose or future classification, sex, parent/litter performance, growth, no terminal exit. |
| Allocated | Pig is already committed to an order, slaughter batch, or future meat workflow. | Active order line, active sales transaction item, future meat order allocation. |
| Exited | Pig already left the farm or died/was removed. | `Status`, `On_Farm`, `Exit_Date`, `Exit_Reason`, sale/slaughter linkage. |

## First Read-Only Build Candidate

Build a `Pig Allocation Readiness` view before any full pork-sales write workflow.

Suggested route:

- `/pig-allocation`

Suggested first backend endpoint:

- `GET /api/pig-weights/pig-allocation-readiness`

First screen behavior:

- read-only
- full-width operational table
- filters for pen, stage/type, sex, purpose, readiness bucket, and weight range
- latest weight and days since weight
- current pen
- litter/sow/boar where available
- current purpose
- sale/slaughter/order linkage where available
- clear reason text for why the pig is in a bucket
- no writes, no automatic classification, no hidden status changes

Useful columns:

| Column | Reason |
| --- | --- |
| Pig / Tag | Operator identity. |
| Type / Sex | Practical sale and breeding decision. |
| Current Pen | Farm movement and inspection. |
| Latest Weight | Sale/slaughter/meat readiness. |
| Days Since Weight | Data freshness. |
| Purpose | Current owner/system intent. |
| Readiness Bucket | Planning summary. |
| Reason | Explainable, not magic. |
| Litter / Parents | Breeding and bloodline context. |
| Existing Link | Shows if already in order or sale transaction. |

## Suggested First Rules

Keep these conservative and visible as reasons, not hidden automation. The first code version can show these as explanation rules before any write action exists.

| Rule | Bucket |
| --- | --- |
| Missing tag, sex, current pen, or latest weight for an active/on-farm pig | Needs Data |
| Weaned pig has enough identity/weight data but `Purpose = Unknown` | Needs Classification |
| Active/on-farm pig below target threshold | Growing |
| Slow grower or underperformer, not useful for breeding/meat/slaughter timing | Livestock Candidate |
| Fast grower from strong litter/parent line | Retain / Breeding Candidate first, then Meat Candidate if not retained |
| Active/on-farm grow-out pig in the meat window and no existing allocation | Meat Candidate |
| Meat-window pig not pre-sold before it exceeds the meat range | Slaughter Candidate |
| Grow-out pig in abattoir target range and no meat order allocation | Slaughter Candidate |
| Older breeding female no longer useful for breeding and fit for sale | Slaughter Candidate |
| Purpose already `Breeding` or similar | Retain / Breeding Candidate |
| Pig appears in active order/sale transaction | Allocated |
| `On_Farm = No` or terminal status | Exited |

Open thresholds:

- Exact live-sale threshold.
- Exact meat-candidate live weight range.
- Whether slaughter candidate and meat candidate can overlap.
- Whether purpose should override weight rules.
- Whether missing recent weight should always take priority.
- What average daily gain counts as slow, normal, or fast by stage.
- How litter quality should be scored: born alive, weaned count, survival %, wean weight, growth, health issues, sow/boar history.
- How long a pig can stay in the meat candidate window before falling back to abattoir slaughter.
- Whether weekly demand/pre-orders should reduce the number of pigs shown as available for abattoir slaughter.

## Settings Needed Before Smart Writes

The allocation model should eventually use editable business settings instead of hard-coded values.

First useful settings:

| Setting | Purpose |
| --- | --- |
| Meat target min/max live weight | Defines the fresh meat candidate window. |
| Meat window expiry / fallback weight | Moves unsold meat candidates toward abattoir slaughter. |
| Abattoir slaughter target min/max weight | Defines current slaughter/abattoir planning. |
| Slow grower ADG threshold | Flags pigs to sell as livestock rather than keep feeding. |
| Fast grower ADG threshold | Flags pigs worth reviewing for breeding or meat. |
| Breeding candidate minimum litter quality | Prevents retaining fast pigs from weak litter/parent lines. |
| Stale weight days | Stops old weights from driving allocation decisions. |
| Older breeding female review age/parity | Flags sows/gilts/older ladies for cull/slaughter review. |

Do not build a settings write page until the first read-only rules are visible and owner-reviewed. The first implementation can show the thresholds it is using and keep them easy to change in code or config.

Settings read-model decision 2026-06-05:

- Added a backend-owned allocation settings object for the first active rules.
- `/api/pig-weights/pig-allocation-readiness` now returns both raw `thresholds` and human-readable `business_rules`.
- `/pig-allocation` displays the active rule labels above the table so the owner can see exactly which meat, abattoir, livestock, growth, litter-quality, and stale-weight thresholds produced the view.
- Settings source is currently `code_defaults`; no settings write page, no Google Sheets setting write, no Supabase write, and no automated allocation action was added.
- This is the bridge toward a later approved settings page or `SYSTEM_SETTINGS` integration once the owner has enough live evidence to tune the values.

Suggested-purpose signal decision 2026-06-05:

- Added a read-only suggested-purpose signal beside the current stored `Purpose`.
- Suggested purpose values currently include `Needs Review`, `Grow Out`, `Livestock Sale`, `Meat`, `Abattoir Slaughter`, `Breeding Review`, `Already Allocated`, and `Closed`.
- Each suggestion includes a reason and confidence level so the owner can review the model before any backend-owned classification action is added.
- This does not update `PIG_MASTER`, `PIG_OVERVIEW`, Supabase, Google Sheets, Telegram, or Meta channels.

Herdmaster purpose-review decision 2026-06-15:

- The immediate operational focus shifts from Ledger sales lead tracking back to Herdmaster because weaned litters can already create real farm attention with no clean resolution path.
- `Weaned - review purpose` is not an emergency alert and not a weaning bug. It means a litter is already weaned but one or more active/on-farm linked piglets still have blank or `Unknown` purpose.
- Herdmaster owns the piglet purpose recommendation workflow after weaning. Breeding analytics feeds it with sow, boar, litter quality, survival, wean weight, and growth context. Butcher can later add meat/slaughter suitability, and Ledger can later add demand pressure.
- Oom Sakkie/Gatekeeper remains the owner approval surface. Humans approve, override, defer, or request a recheck; the backend performs any approved write.
- The first full review surface should be `/purpose-review`, with optional litter focus such as `/purpose-review?litter_id=LIT-2026-8A0F`.
- The page should present a table of active/on-farm piglets needing purpose review, including pig/tag, litter, sow/boar, sex, pen, wean date/weight, latest weight, ADG, growth band, litter quality, stored purpose, suggested purpose, confidence, reason, and owner action.
- Human actions should include approve selected, approve all visible/high-confidence rows, approve one row, override purpose, recheck one row, and leave `Needs Data` rows unresolved until missing data is fixed.
- The approved backend action may update `PIG_MASTER.Purpose`, `PIG_MASTER.Updated_At`, and append an audit note to `PIG_MASTER.General_Notes`.
- The purpose review action must not update status, on-farm state, sales availability, orders, slaughter transactions, meat orders, stock allocation, Telegram, Meta, Chatwoot, WhatsApp, or Supabase.
- Supported stored purposes stay aligned to the existing pig master values for now: `Breeding`, `Grow_Out`, `Sale`, `Replacement`, `House_Use`, and `Unknown`.
- Suggested-purpose mapping is deliberately conservative: `Grow Out` maps to `Grow_Out`, `Livestock Sale` maps to `Sale`, `Breeding Review` maps to `Breeding`, and meat/abattoir suggestions map to `Grow_Out` until the later allocation/order workflow can own actual meat or slaughter commitment.
- Recheck/question-one is a no-write Herdmaster analysis packet built from the current allocation signals. It should explain why the recommendation exists and help the owner decide, not run a hidden classifier or mutate farm data.
- Wean date and wean weight must come from `PIG_MASTER`, not only `PIG_OVERVIEW`, because `PIG_OVERVIEW` is a formula view and may not expose all lifecycle fields needed by Herdmaster.
- The mark-weaned action should carry `Wean_Date`, `Litter_Size_Weaned`, and, when available, each piglet's latest weight into `PIG_MASTER.Wean_Weight_Kg` so the next purpose review has maximum useful data without manual sheet edits.
- If latest weights are missing when the owner asks to use them as wean weights, the backend should stop the weaning action and ask for weights instead of saving a weak review state.
- `Purpose = Unknown` should keep the row in owner approval, but it must not stop Herdmaster from suggesting a useful purpose. Unknown-purpose rows with enough data should still produce `Breeding Review`, `Livestock Sale`, `Meat`, `Abattoir Slaughter`, or `Grow Out` with a visible reason and confidence.
- Purpose attention should not appear immediately after weaning. First rule: wait 14 days after weaning before surfacing final purpose review.
- If the 14-day window has passed but no post-wean weight exists after the wean date, dashboard attention should say `Post-wean weight needed` and route to weight capture.
- Once a post-wean weight exists after the 14-day window, dashboard attention should say `Purpose review due` and route directly to `/purpose-review?litter_id=...`.
- Implementation status 2026-06-15: this Herdmaster phase is local-ready, not yet farm-proven. The local build includes `/purpose-review`, no-write recheck analysis, owner approval writes limited to `PIG_MASTER.Purpose`/`Updated_At`/`General_Notes`, mark-weaned latest-weight carryover into `Wean_Weight_Kg`, `PIG_MASTER` enrichment for wean fields, 14-day post-wean attention timing, weight-needed routing, and direct navigation to the correct work page. The next real farm test must verify those functions on a future weaning/post-wean-weight cycle before closing this phase as live-verified.
- After this Herdmaster phase is visible and tested on one real litter, return to the Sales Outreach / Lead Tracking rail.

Meat planning read-model decision 2026-06-05:

- Added first read-only meat planning layer from the allocation readiness signals.
- `/api/pig-weights/meat-planning` groups candidate pigs into `ready_now`, `next_14_days`, `next_30_days`, `future`, and `fallback_abattoir`.
- `/meat-planning` shows meat pipeline counts, minimum preorder demand needed now/within 30 days, active meat/abattoir rules, and the candidate table.
- This is not a meat order system yet. It creates no preorders, deposits, customer records, pig allocations, Telegram messages, Meta posts, Supabase writes, or Google Sheets writes.

Temporary demand scenario decision 2026-06-05:

- Added browser-only expected demand inputs to `/meat-planning` for demand now and demand within 30 days.
- The page calculates visible surplus/shortfall against the read-only meat pipeline and warns when demand is higher than the current 30-day pipeline.
- These values are not saved to browser storage, Supabase, Google Sheets, orders, or any backend table.
- This is only for testing demand assumptions before designing real preorder/deposit records.

Growth band decision 2026-06-05:

- Use kg/day in the UI and API, where `0.100 kg/day` means 100 g/day.
- Show lifetime average daily gain first, calculated from latest weight over age/days on farm where possible.
- Keep post-wean average daily gain as a separate context line, because it can explain recent trend after weaning without hiding the lifetime view.
- First read-only growth bands:
  - `Extremely Slow`: below `0.100 kg/day`
  - `Slow`: `0.100` to below `0.200 kg/day`
  - `Below Target`: `0.200` to below `0.300 kg/day`
  - `Steady`: `0.300` to below `0.400 kg/day`
  - `Good`: `0.400` to below `0.500 kg/day`
  - `Exceptional`: `0.500 kg/day` or higher
- Target direction: push the herd toward `0.500 kg/day` where realistic, while using trend and litter quality before making retention/meat/slaughter decisions.

Readiness timing decision 2026-06-05:

- Add estimated readiness dates from lifetime ADG so the page can support preorder and customer timing conversations.
- Estimate meat window readiness from the configured meat minimum weight.
- Estimate abattoir readiness from the configured abattoir minimum weight.
- Keep these estimates read-only and explainable; they are planning signals, not promises.
- First abattoir/slaughter target range should reflect the current fallback outlet: `80` to `95 kg`, with `80-90 kg` treated as the practical sweet spot during owner review.

Self-selling system direction 2026-06-05:

- Long-term goal: the system should become a weekly selling engine, not only an internal report.
- Extremely slow and slow growers should feed livestock-sale recommendations as soon as practical, because the business goal is to reduce feed cost and move underperformers.
- Meat-window pigs should feed meat preorder/interest generation first once the meat business is active.
- Abattoir/slaughter remains the fallback outlet for grow-out pigs that are not sold through meat in time.
- Future Telegram summaries and Meta-compliant Facebook/Instagram post drafts should be generated from the same read-only allocation signals.
- Do not auto-post or auto-message yet. First build read-only outlet priorities and recommended actions, then review compliance wording and approval flow before any automation.

Sales outreach and lead tracking direction 2026-06-14:

- Oom Sakkie/Jarvis remains the owner command center and approval channel.
- Ledger owns business/sales strategy advice.
- Beacon should eventually draft public/social demand-generation content.
- Sam remains the customer conversation/order-intake agent in Chatwoot/WhatsApp.
- The backend is the source of truth for campaigns, leads, approval state, orders, deposits, stock/allocation, and traceability.
- Telegram must not become the customer sales tunnel. It is for owner alerts, summaries, and approval prompts.
- The preferred flow is inbound demand generation: Ledger identifies opportunity, Beacon drafts public/status/channel copy, owner approves, customers reply inbound, Sam handles the conversation, and the backend tracks the lead/order state.
- The first customer-facing build must be tracking only: no direct sending, no Chatwoot/n8n/WhatsApp calls, no public posting, no quote/order creation, no stock reservation, and no allocation writes.

The Sales Outreach / Lead Tracking rail should track:

| Field | Purpose |
| --- | --- |
| Campaign source | Identifies whether the lead came from ready-meat preorder, social post, direct known buyer, inbound Chatwoot, WhatsApp status, owner note, or another source. |
| Lead status | Tracks practical sales state such as interested, asked price, needs callback, deposit pending, not interested, or order ready for approval. |
| 24-hour WhatsApp state | Shows whether Sam may reply inside the customer-service window, whether the window is closed, whether a template is required, or whether the owner must handle it manually. |
| Last inbound time | Supports WhatsApp window decisions. |
| Opt-in state | Prevents uncontrolled outreach assumptions. |
| Interest details | Captures half/full carcass, cut set, location, timing, payment/deposit preference, and customer notes as structured context. |
| Linked order/preorder | Connects lead tracking to a future order/deposit workflow without using chat history as truth. |
| Owner approval needs | Surfaces price approval, follow-up approval, deposit follow-up, or Sam handoff review. |

Implementation decision 2026-06-14:

- Add append-only `oom_sakkie_sales_leads` and `oom_sakkie_sales_lead_events` tables.
- Add review-gated backend routes for listing/recording leads and lead events.
- Add an Oom Sakkie read-only `sales_lead_tracking_status` tool and include it in the daily command brief.
- Keep all authority flags false: no customer send, no Chatwoot/n8n call, no quote, no order, no stock change, no dispatch, no runtime/prompt change, no public output, and no farm-data write.
- This rail is a tracking and approval queue only. Future Sam/Chatwoot consumers must be reviewed separately before they can create or update these records from live conversations.

Resume status 2026-06-15:

- Sales campaign and lead migrations were applied successfully.
- Live/local route checks confirmed the queues read cleanly and all send/order/stock authority flags remain false.
- The Oom Sakkie Ledger Sales Workbench now includes owner manual lead capture through `POST /api/oom-sakkie/sales-leads`.
- The form is for inbound/manual tracking only and does not contact customers or create orders.
- Next proof step: record one real owner-approved inbound/manual lead and confirm it appears in Oom Sakkie summaries before calling the rail live-verified.

## Backend-Owned Actions Later

These actions should not be built as direct table edits in the UI.

| Future action | Owner | Notes |
| --- | --- | --- |
| Mark litter weaned | Existing backend action | Keep as source of weaning truth. |
| Classify pig purpose/allocation | Herdmaster purpose review action | Owner-approved only. Should explain old/new purpose, reason, confidence, and actor. |
| Confirm slaughter pig exits | Existing backend action | Explicit operator confirmation, not automatic payment side effect yet. |
| Create meat order/deposit | Future Phase 11 action | Must include customer, product, deposit, expected slaughter week. |
| Assign pig to meat order | Future Phase 11 action | Should block double allocation. |
| Record carcass/packed yield | Future Phase 11 action | Needs actual weights from slaughter/butchery. |
| Complete delivery/payment | Future Phase 11 action | Must update sale/payment state and reporting. |

## Data Gaps To Leave Open

Do not block Phase 11A on these, but do not pretend they are solved.

- Real bulk weight upload still needs live farm testing.
- Actual carcass weights are not consistently captured yet.
- Butchery, packaging, transport, and delivery costs need real records before margin reporting is trusted.
- Customer meat-order/deposit workflow is not designed yet.
- Cold-chain, delivery proof, labels, and packaging process need operating decisions.
- Automated breeding/purpose recommendations need more live data.
- Wean weight and average daily gain need to be consistently available before purpose suggestions can be trusted.
- Litter quality scoring needs a visible formula before the system can recommend retaining breeding animals.
- Meat pre-order demand needs a source before the system can say how many meat candidates are actually needed this week.

## Recommended Implementation Sequence

1. Build the read-only pig allocation readiness endpoint.
2. Build the read-only full-width `/pig-allocation` page.
3. Add growth context: wean weight, latest weight, average daily gain, days since wean/latest weight, and age/stage.
4. Add litter quality context: sow/boar, born alive, weaned, survival, health flags, and litter performance.
5. Let owner use it and note where the buckets or thresholds are wrong.
6. Add configurable thresholds or documented constants once real use shows what matters.
7. Add a read-only suggested-purpose reason, still with no writes.
8. Only then add a backend-owned classification/allocation action.
9. Start meat-order workflow planning after allocation is trusted enough to identify candidate pigs.

## Non-Goals For Phase 11A

- No full meat-order form.
- No customer deposit workflow.
- No automatic pig purpose changes.
- No automatic slaughter/meat allocation.
- No margin/profit claims from incomplete cost data.
- No replacement of the existing live-pig order flow.
