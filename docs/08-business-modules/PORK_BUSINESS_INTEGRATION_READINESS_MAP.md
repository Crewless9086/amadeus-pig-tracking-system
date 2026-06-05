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

## Backend-Owned Actions Later

These actions should not be built as direct table edits in the UI.

| Future action | Owner | Notes |
| --- | --- | --- |
| Mark litter weaned | Existing backend action | Keep as source of weaning truth. |
| Classify pig purpose/allocation | Future backend action | Should explain old/new purpose and actor. |
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
