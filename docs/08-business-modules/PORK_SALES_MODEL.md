# Pork Sales Business Module

## Status

Planning source document. Not an implementation backlog yet.

## Purpose

This file captures the target business model for Amadeus Farm pork sales so it can be refined before system design starts.

Use this file for owner edits, assumptions, pricing changes, operating notes, and business rules. Implementation tasks should stay out of this file until the module is deliberately moved into `docs/00-start-here/NEXT_STEPS.md`.

## Strategic Direction

Amadeus Farm is moving from only selling live pigs into a dual sales model:

1. Live slaughter-ready pig sales.
2. Pre-ordered full or half carcass meat sales through legal slaughter and butchery facilities.

The goal is to increase profit per pig, reduce waste, build a premium sustainable pork brand, and create trusted customer relationships.

The operating model must remain simple, legal, traceable, and scalable.

## Core Principle

No pig is slaughtered for meat sales unless it is pre-sold.

This protects cashflow and avoids unsold frozen stock, waste, unnecessary feed costs, overproduction, storage pressure, and poor planning.

## Sales Modules

### Module A: Live Pig Sales

Live pigs are sold from around 60 kg upward, depending on customer need.

Current historical heavier-live reference:

| Live weight | Price |
| ---: | ---: |
| 80-84 kg | R2,800 |
| 85-89 kg | R2,900 |
| 90-95 kg | R3,000 |

Planning note:

- Consider a 60 kg+ slaughter-ready live category for faster turnover.
- Keep live sales as the backup outlet for pigs not allocated to meat pre-orders.

### Module B: Assisted Slaughter Facility Option

For live pig buyers, Amadeus may assist by coordinating legal slaughter-facility access.

Example flow:

1. Customer buys live pig.
2. Amadeus helps coordinate slaughter at a designated legal facility.
3. Customer collects carcass from the slaughter facility.
4. Extra coordination/slaughter handling fee may be around R250 per pig.

Compliance note:

- Amadeus must not appear to operate as an unregistered abattoir.
- Slaughter must happen at a legal facility.

### Module C: Pre-Ordered Carcass Meat Sales

This is the main profit-building model.

Customers order:

- Full carcass.
- Half carcass.
- Later: custom cut option.

The pig is only slaughtered once the order is confirmed and paid/deposited.

Suggested pricing:

| Product | Price |
| --- | ---: |
| Full carcass standard cut | R120-R130/kg |
| Half carcass standard cut | R130-R140/kg |
| Custom cut option | R140-R150/kg |

Planning note:

- Earlier R100/kg pricing is likely too low once VAT, butchery, packaging, delivery, slaughter, and admin are included.

## Working Production Assumptions

Preferred meat model slaughter target:

- About 60 kg live weight.

Reasons:

- younger meat
- leaner pork
- faster turnover
- lower feed cost
- better cashflow
- suitable for half-carcass household orders

Yield estimates:

| Item | Estimate |
| --- | ---: |
| Live weight | 60 kg |
| Carcass yield | 43-45 kg |
| Packed usable meat | 38-42 kg |

Current planning assumption:

- Use 42 kg saleable carcass weight per 60 kg pig until better farm data replaces it.

## Example Margin Model

At R130/kg:

- 42 kg x R130 = R5,460 incl. VAT.
- If VAT registered: R5,460 / 1.15 = R4,748 ex VAT.

Estimated direct cost per pig:

| Cost item | Estimate |
| --- | ---: |
| Feed cost allocation | R1,000 |
| Slaughter fee | R350 |
| Butchery/cutting/packing labour | R850 |
| Packaging | R200 |
| Delivery/logistics | R200 |
| Total direct cost | R2,600 |

Estimated clean profit:

- R4,748 - R2,600 = R2,148 profit per pig.

Target example:

- R50,000 clean monthly target / R2,148 = about 24 pigs per month.
- Practical target: 24-25 meat pigs per month, about 6 pigs per week.

Risk note:

- At R100/kg the required volume may approach 45-50 pigs per month, which is likely too much pressure for the current system.

## Feed Planning Impact

Estimated feed required to grow one pig to 60 kg:

- 150-180 kg feed per pig.

For 25 pigs/month:

| Calculation | Feed required |
| --- | ---: |
| 25 pigs x 150 kg | 3,750 kg |
| 25 pigs x 180 kg | 4,500 kg |

Planning target:

- Meat model needs roughly 4-4.5 tons feed per month for slaughter pigs alone.
- Total farm planning should assume 5+ tons/month feed capacity before scaling aggressively.

Feed sources to refine:

- bought feed
- lucerne
- barley sprouts
- green forage
- vegetable waste
- farm-grown protein sources
- crop residues
- future algae/duckweed/BSF-style systems

## Standard Cut Sets

The first version should avoid unlimited custom choices.

### Set A: Family Freezer Pack

Default balanced freezer pack:

- pork chops
- leg portions or roasts
- shoulder roasts
- belly strips
- ribs
- mince or stew meat
- bones for soup/stock

### Set B: Braai Pack

South African buyer-friendly pack:

- chops
- rashers/belly strips
- ribs
- shoulder steaks
- sosatie/stew cubes
- mince or sausage meat option

### Set C: Lean Pack

For health-conscious customers:

- lean chops
- leg steaks
- lean shoulder cuts
- mince
- stew cubes
- fewer fatty belly cuts

### Set D: Budget Bulk Pack

For value-focused families:

- larger roasting cuts
- mince
- stew meat
- soup bones
- shoulder
- mixed chops
- less detailed trimming

### Custom Cut Option

Later only, at higher price:

- R140-R150/kg suggested.
- Higher deposit required.
- Limited checklist, not unlimited custom instructions.

## Payment Terms

Standard carcass order:

- 50% deposit to confirm.
- Balance due before delivery or collection.

Custom cut order:

- 70% deposit.
- Balance due before delivery or collection.

Live pig order:

- 30% deposit to reserve.
- Balance before collection.

Final payment rule:

- No full payment means no delivery.

## Weekly Operating Rhythm

Suggested first rhythm:

| Day | Work |
| --- | --- |
| Monday | close orders, confirm deposits, finalize cut sets, allocate pigs |
| Tuesday/Wednesday | confirm slaughter bookings, prepare delivery/collection schedule, print labels and customer notes |
| Thursday | pigs sent to slaughter facility |
| Friday | butchery/cutting/packing, final weights confirmed, final invoices issued |
| Saturday | local delivery or collection |

Scaling approach:

- Start with 1 pig/week test.
- Then 2 pigs/week.
- Then 3 pigs/week.
- Later target 6 pigs/week.

Do not jump straight to 25 pigs/month until the process is proven.

## Packaging And Brand Experience

Packaging must communicate:

- sustainability
- cleanliness
- trust
- personal care
- premium but not fake luxury

Each order should include:

- proper meat label: product name, weight, pack date, freeze/use guidance, farm brand, batch/order number
- simple sustainability message
- personal thank-you card
- farm postcard
- "you helped build this" note

Brand principle:

- Customers must feel they are supporting the building of a better farm, not just buying pork.

## Loyalty And Relationship Strategy

Avoid loud discounts.

Use quiet appreciation:

- priority access to next batch
- small extra pack
- free bones for broth
- handwritten birthday/thank-you note
- early access to limited products
- founding customer recognition
- seasonal farm postcard series

Do not train customers to wait for discounts.

## Delivery Model

### Phase 1: Local Collection/Delivery

Start with:

- Riversdale
- Albertinia
- Still Bay
- nearby towns

Use:

- cool box on bakkie
- later van setup
- fixed delivery days

### Phase 2: Regional Route Delivery

Expand only after local process is stable:

- Mossel Bay
- George
- Heidelberg
- Swellendam

### Phase 3: National Delivery

Only after:

- packaging is tested
- courier partner confirmed
- frozen product holds temperature
- temperature records are proven
- labels and compliance are ready

## Processing Risk

Current plan:

- use existing slaughter facility
- use butcher/blockman for cutting and packing

Risk:

- The butcher may become a competitor or bottleneck.

Mitigation:

- do not share full customer database
- do not share full strategy
- get more than one processing option
- standardize cut sheets
- eventually hire a blockman one day per week
- work toward own legal cutting/packing facility

## Future System Capability Areas

These are business capability areas, not implementation tasks yet.

### Customers

- name, phone, location, language
- previous orders
- loyalty status
- notes/preferences

### Orders

- live/full/half/custom
- selected cut set A/B/C/D
- estimated and final weight
- price/kg
- deposit paid
- balance paid
- delivery/collection status

### Pigs

- pig ID and tag number
- live weight
- availability
- suggested purpose after weaning
- growth-potential classification
- revenue stream allocation
- allocated order
- slaughter date
- carcass weight
- batch number

## Weaning Classification And Revenue Stream Logic

Planning concept:

- Once a litter is weaned, the system should help classify each piglet instead of leaving every decision manual.
- Classification should use birth weight, weaning weight, growth rate, litter quality, parent/litter history, and owner-defined rules.
- The system should suggest a purpose, not silently force one.

Possible suggested purposes:

| Suggested purpose | Meaning |
| --- | --- |
| Breeding candidate | Hold back because the animal comes from a good litter, has good growth potential, or matches breeding criteria. |
| Grow-out | Keep growing because the animal is performing well and may become more valuable at heavier weight. |
| Sale | Make available for live sale when growth potential is below the grow-out/breeding threshold but still commercially saleable. |
| Slaughter-ready path | Move into the meat/carcass stream once an animal reaches the preferred slaughter weight and has not sold through live-sale channels. |

Business rule direction:

- Good litters and strong performers may be held back for breeding or grow-out.
- Fast growers can be pushed toward grow-out or slaughter-ready meat value.
- Slightly weaker commercial animals can go into sale stock earlier.
- A sale pig that does not sell before reaching slaughter-ready weight should be eligible to move into the higher-value meat/carcass stream if demand exists.

Important design question:

- Decide whether slaughter-ready pigs are a separate sheet/table/view or a filtered revenue stream over the same pig records.

Initial preference:

- Keep one pig source of truth.
- Use purpose, sales status, weight band, allocation status, and revenue-stream fields/views to separate live sale vs slaughter-ready/meat-focused animals.
- Avoid duplicating pig records into a separate meat sheet unless there is a clear processing/batch reason.

Future planning fields to consider:

- `Suggested_Purpose`
- `Purpose_Confidence`
- `Classification_Reason`
- `Revenue_Stream`
- `Revenue_Stream_Status`
- `Slaughter_Eligible`
- `Slaughter_Target_Date`
- `Slaughter_Allocation_Order_ID`
- `Growth_Rate_To_Weaning`
- `Litter_Performance_Class`

### Processing

- slaughter facility
- butchery provider
- cut set
- packing date
- final packed weight
- yield percentage

### Delivery

- route
- delivery date
- cold box used
- driver
- customer confirmation
- delivery status

### Finance

- gross sale
- VAT
- slaughter cost
- butchery cost
- packaging cost
- delivery cost
- feed allocation
- clean profit per pig
- clean profit per batch/month

### Branding

- postcard image used
- thank-you note included
- loyalty gift included
- customer feedback

## Main Risks To Watch

| Risk | Guardrail |
| --- | --- |
| Underpricing | price from margin backwards |
| Over-customization | start with 4 cut sets only |
| Cold-chain failure | start local, test packaging, record temperatures |
| Feed shortage | use pre-orders, 60 kg target, and live-sales backup |
| Cashflow pressure | deposit and full payment before delivery |
| Butcher dependency | use short-term, build own options over time |

## Planning Inputs To Add Next

Add small updates here as the business plan gets clearer:

- confirmed legal slaughter facility options
- butchery provider options and pricing
- packaging costs and suppliers
- deposit/payment policy decisions
- first local delivery towns and delivery fee rules
- preferred first cut-set wording for customers
- VAT assumption and accounting treatment
- first realistic pilot size
- target customer profiles
- brand wording examples
- label requirements
- cold-chain requirements

## Planning Discussion Log

Use this section to keep track of where ideas came from and how the thinking developed.

Format:

- **Planning suggestion**: initial system/business planning idea.
- **Advisor/partner response**: external or partner feedback.
- **Codex comment**: system/planning interpretation.
- **Owner comments**: Charl's notes, decisions, concerns, or changes.

### Discussion 2026-05-17: Pre-Implementation Structure

#### 1. Pilot Scope

Planning suggestion:

- Start with a deliberately small pilot.
- Suggested first structure: 1 pig/week, simple product menu, local delivery/collection only, no custom cuts.

Advisor/partner response:

- Agree with starting small, but recommend the pilot focus more narrowly on half carcass orders first.
- Suggested pilot: half carcass, Set A only, local delivery only, 1 pig/week.
- Reason: half carcass is likely the largest first market because full carcass quantity may create freezer-space and price hesitation.

Codex comment:

- This is a strong correction. The first pilot should reduce operational complexity and customer friction.
- The system should support full carcass in the model, but the first test offer can be half carcass only.
- Recommended planning label: `Pilot_V1_Half_Carcass_Set_A_Local`.

Owner comments:

This is VERY good thinking already.
The direction is correct.

What I like most:

* you are thinking operationally,
* emotionally,
* financially,
* and transparently at the same time.

That combination is rare.

Now as your advisor/partner, I’m going to inspect this from:

* customer psychology,
* operational sustainability,
* profitability,
* legal clarity,
* scalability,
* and reputation risk.

Because this pilot phase is not really about profit yet.

It is about:

# proving the SYSTEM.

And that mindset is critical.

---

# 🔍 ANALYSIS OF CURRENT PILOT COMMENTS

---

# ✅ STRONG POINTS IDENTIFIED

## 1. Starting Small

Correct.

This massively reduces:

* operational chaos,
* delivery failures,
* packaging mistakes,
* butcher confusion,
* customer dissatisfaction.

This is the correct move.

---

## 2. Half Carcass Focus

Very smart.

This reduces:

* freezer-space objections,
* upfront cost shock,
* hesitation.

Most first-time premium pork buyers do not want:

* an entire pig.

Half carcass is psychologically easier.

---

## 3. Set A Only

Excellent.

This protects:

* butcher workflow,
* consistency,
* packaging,
* delivery planning.

Too much customization early would destroy the pilot.

---

## 4. “Single Pig Allocation”

VERY IMPORTANT AND VERY GOOD.

This:

> “sales is based on the selected pig and not made up from multiple pigs”

is actually one of your strongest future premium positioning points.

Why?

Because it creates:

# traceability.

That matters massively in premium food.

Customers subconsciously trust:

* transparency,
* identifiable sourcing,
* realness.

This separates you from:
industrial mixed-batch meat.

This is extremely valuable branding.

---

# ⚠️ IMPORTANT ISSUE I SEE

This needs clearer wording operationally:

> “final invoice sent after final weight”

This can create:

# customer anxiety.

Why?

Because customers fear:

* surprise pricing,
* unknown totals,
* being overcharged.

You must handle this VERY carefully.

---

# ✅ RECOMMENDED SOLUTION

Instead of:

> “price unknown until final invoice”

You should create:

# ESTIMATED RANGE SYSTEM.

---

# Recommended wording:

Example:

### Selected Pig

* Estimated live weight: 62kg
* Estimated packed yield: 40–43kg
* Estimated total price range: R4,800–R5,300

Then:

* customer pays deposit,
* final invoice adjusted to actual packed weight.

This creates:

* trust,
* predictability,
* transparency.

VERY important psychologically.

---

# ⚠️ ANOTHER IMPORTANT ISSUE

## Pig Size Variability

You mentioned:

> “different slaughter stages ranging from 60kg and up”

This is correct operationally.

BUT:
you must avoid:

# inconsistent customer expectation.

---

# PROBLEM

If:
Customer A gets:

* 39kg packed yield

and Customer B gets:

* 46kg packed yield

they may compare and feel:

* treated differently,
* confused.

---

# ✅ SOLUTION

You need:

# WEIGHT CATEGORIES.

Example:

| Category | Live Weight | Estimated Packed Yield |
| -------- | ----------- | ---------------------- |
| Small    | 60–64kg     | 38–41kg                |
| Medium   | 65–69kg     | 41–44kg                |
| Large    | 70–75kg     | 44–48kg                |

This is MUCH cleaner operationally.

It also helps:

* pricing,
* forecasting,
* customer expectation,
* butcher planning.

---

# 🚨 IMPORTANT STRATEGIC WARNING

Do NOT let customers “choose the biggest pig.”

That creates:

* inventory imbalance,
* difficult conversations,
* operational headaches.

Instead:
customers choose:

# CATEGORY.

NOT specific pig.

---

# BUT…

Internally:
you absolutely SHOULD track:

* Pig ID,
* slaughter yield,
* carcass yield,
* feed efficiency,
* customer feedback.

That data becomes GOLD later.

---

# 🧠 VERY IMPORTANT PSYCHOLOGY POINT

You mentioned:

> “pilot run” and “journey”

Correct instinct.

But:
be careful not to make customers feel like:

# guinea pigs.

---

# WRONG FEELING

“We are testing and figuring things out.”

---

# CORRECT FEELING

“You are part of helping us build something special from the beginning.”

Huge difference.

---

# RECOMMENDED POSITIONING

Not:

> “pilot”

Instead:

# “Founding Batch”

OR

# “First Seasonal Release”

OR

# “Limited Founding Orders”

This feels:

* exclusive,
* premium,
* community-driven.

NOT experimental.

That is a very important branding difference.

---

# 🔥 VERY IMPORTANT FUTURE INSIGHT

You are accidentally building something VERY powerful:

# Scarcity.

Because:

* only certain pigs,
* only certain quantities,
* only weekly batches,
* pre-order only.

This creates:

# demand tension.

That is extremely valuable.

Do NOT lose that later by over-scaling too quickly.

---

# ⚠️ BIG OPERATIONAL ISSUE TO FLAG NOW

# FINAL WEIGHT TIMING

You must define:

## when final weight is confirmed.

Recommended:

### After:

* slaughter,
* trimming,
* cutting,
* packing.

NOT directly after carcass weight.

Because:
customers care about:

# what arrives in the box.

Not hanging carcass numbers.

---

# 🧠 STRONG RECOMMENDATION

Your invoice should eventually show:

| Item          | Weight |
| ------------- | -----: |
| Chops         |   x kg |
| Roast cuts    |   x kg |
| Belly/rashers |   x kg |
| Ribs          |   x kg |
| Mince/stew    |   x kg |
| Bones         |   x kg |
| TOTAL         |   x kg |

This creates:

* professionalism,
* trust,
* perceived value.

---

# ⚠️ IMPORTANT DELIVERY ISSUE

You need:

# DELIVERY WINDOW RULES.

Example:

* deliveries only Saturdays
* customer must be available
* cooler/freezer ready
* collection within set time

Otherwise:
meat logistics becomes chaos.

---

# 🚨 MOST IMPORTANT ISSUE I SEE

Honestly?

# Emotional overload.

Your instinct is:

* personal,
* warm,
* relationship-driven.

GOOD.

BUT:
you must avoid:

# operational exhaustion.

You cannot:

* handwrite essays,
* custom message everyone,
* over-personalize endlessly,
  once scale grows.

---

# ✅ SOLUTION

Create:

# SYSTEMIZED PERSONALIZATION.

Example:

* printed postcard
* short handwritten signature
* small custom note section
* rotating farm photos
* standard thank-you insert

Feels personal.
Still scalable.

VERY important.

---

# 🔥 STRONGEST RECOMMENDATION I WOULD ADD

Add:

# “Customer Feedback Loop”

After delivery:

* ask about:

  * taste,
  * packaging,
  * cuts,
  * quantity,
  * delivery,
  * freezer usability.

Because:
the pilot is REALLY:

# data collection.

Not just selling meat.

---

# RECOMMENDED FINAL ADDITION TO THIS SECTION

## Founding Batch Philosophy

Example:

> “The first batches are intentionally limited in volume to ensure product quality, customer experience, and operational consistency while Amadeus Farm develops a long-term sustainable pork system.”

That statement is powerful.

It tells customers:

* intentional,
* premium,
* careful,
* quality-first.

NOT:
small because struggling.

Huge psychological difference.


#### 2. Product Menu

Planning suggestion:

- Define customer-facing options before system design.
- Include estimated packed weight, price/kg, deposit requirement, balance rule, and delivery/collection expectation.

Advisor/partner response:

- Product definition is important, but should be positioned as a premium farm supply offer, not just a meat-selling menu.
- The customer relationship and trust story are part of the product.

Codex comment:

- Product records should eventually include both operational fields and customer-facing description fields.
- Avoid wording that sounds like commodity pork.
- The first product menu should be short enough for Sam, web app, and printed/WhatsApp material to use consistently.

Owner comments:

- Pending.

#### 3. Customer Experience System

Planning suggestion:

- Add customer journey steps: inquiry, confirmation, deposit, slaughter confirmation, packaging updates, delivery reminder, thank-you follow-up, repeat engagement.

Advisor/partner response:

- This is missing and very important.
- The experience is part of the product.
- Customers remember how they felt more than the exact cuts.

Codex comment:

- This should become its own future capability area.
- The system should eventually track communication milestones, not only order status.
- Candidate future statuses: `Inquiry`, `Deposit_Requested`, `Deposit_Confirmed`, `Slaughter_Booked`, `Processing`, `Packed`, `Ready_For_Delivery`, `Delivered`, `Followed_Up`.

Owner comments:

- Pending.

#### 4. Cold Chain And Food Safety

Planning suggestion:

- Add cold-chain assumptions and traceability fields before implementation.

Advisor/partner response:

- This risk is underestimated and needs a dedicated section.
- One bad delivery can damage trust, create illness risk, and harm the brand permanently.
- Need cold box sanitation, ice pack checks, transport duration limits, temperature checks, delivery windows, customer collection rules, and failed delivery procedure.

Codex comment:

- Cold-chain rules must be treated as operating controls, not optional notes.
- The data model should eventually support traceability from pig ID to slaughter date, butcher batch, order ID, and delivery route.
- Before any national or regional courier model, temperature evidence and failed-delivery handling need to be defined.

Owner comments:

- Pending.

#### 5. Brand Identity Rules

Planning suggestion:

- Define brand tone and customer offer before building customer-facing automation.

Advisor/partner response:

- Amadeus should be built as a relationship-driven premium farm supply system, not a meat-selling system.
- Brand pillars should include honest farming, low-stress animals, sustainability, traceable meat, personal relationships, premium but approachable, and no industrial farming mentality.
- Tone should be grounded, calm, authentic, respectful, and quietly premium.

Codex comment:

- This should guide Sam's future wording, packaging text, document templates, labels, and web app customer-facing content.
- The system should not use discount-heavy wording or supermarket-style commodity language.
- Future prompt/document rules should reference these brand pillars.

Owner comments:

- Pending.

#### 6. Sustainability Tracking

Planning suggestion:

- Track sustainability as operational and brand proof over time.

Advisor/partner response:

- This is a large future advantage.
- Track reduced bought feed, spekboom planted, waste reduction, water reuse, composting, feed grown on farm, and packaging sustainability.
- Measurable statements like "customer orders helped reduce commercial feed usage by 12%" can become powerful.

Codex comment:

- Sustainability claims must be backed by measured data before being used publicly.
- This may become a reporting module later, linked to feed, crops, waste, water, and packaging.
- Treat sustainability as proof, not marketing decoration.

Owner comments:

- Pending.

#### 7. Production Bottleneck Planning

Planning suggestion:

- Add bottleneck planning before scaling.

Advisor/partner response:

- Scaling usually fails from bottlenecks, not lack of customers.
- Track feed production, slaughter slot availability, butcher capacity, packaging speed, delivery capacity, freezer storage, and admin/time management.

Codex comment:

- The first operational dashboard for this module should probably show capacity, not only sales.
- Candidate future capacity fields: pigs/week available, slaughter slots/week, butchery capacity/week, delivery slots/day, packaging stock, freezer capacity, feed capacity.
- This should prevent accepting more orders than the farm can fulfill well.

Owner comments:

- Pending.

#### 8. Waste Recovery And By-Products

Planning suggestion:

- Add by-product planning once the core process is stable.

Advisor/partner response:

- This is a major opportunity for margin, sustainability, and story value.
- Potential future streams: dog food, broths, rendered fat, bones, organs, compost systems.

Codex comment:

- Do not add by-products to the first customer offer.
- Track them as future recovery streams after the main carcass process is reliable.
- Some by-products may have their own compliance and packaging rules.

Owner comments:

- Pending.

#### 9. Delivery Zone Strategy

Planning suggestion:

- Start local and expand only after process stability.

Advisor/partner response:

- Delivery should be organized by zones because delivery can destroy margins quickly.
- Proposed zones:
  - Zone 1: Riversdale, Albertinia, Still Bay.
  - Zone 2: Mossel Bay, George, Heidelberg.
  - Zone 3: Cape Town and Garden Route courier/regional routes.
  - Zone 4: national delivery, future only.

Codex comment:

- Delivery zone should become a pricing and capacity input, not just an address label.
- The system should eventually know which towns belong to which zone and whether the order is eligible for delivery or collection only.

Owner comments:

- Pending.

#### 10. Capacity Protection Rules

Planning suggestion:

- Define order limits and cutoffs before opening the offer broadly.

Advisor/partner response:

- Need maximum pigs/week, maximum delivery slots/day, cutoff order dates, and cutoff slaughter confirmations.
- These rules protect quality, prevent overload, and reduce burnout.

Codex comment:

- This is one of the most important safeguards for the system.
- The order workflow should eventually refuse or waitlist orders once weekly capacity is full.
- Avoid relying on memory/manual judgment once demand increases.

Owner comments:

- Pending.

#### 11. Failure Scenarios

Planning suggestion:

- Define what happens when the process fails before building automations.

Advisor/partner response:

- Professional systems are defined by how they handle problems.
- Scenarios to plan: slaughter delay, butcher delay, freezer failure, delivery delay, customer cancellation, low carcass yield, packaging shortage, power outage, vehicle breakdown.

Codex comment:

- This should become an operations playbook and later a system status/exception model.
- Each failure should eventually have: trigger, owner, customer message, financial rule, and recovery action.
- Do not automate customer promises until failure wording is agreed.

Owner comments:

- Pending.

#### 12. Pricing And Underpricing Risk

Planning suggestion:

- Price from margin backwards, not from what feels cheap.

Advisor/partner response:

- Biggest current risk is underpricing.
- Avoid comparison to commodity pork, auction pricing, and supermarket thinking.
- The model is traceable, sustainable, premium, direct, and relationship-based.

Codex comment:

- This should become a hard planning rule.
- Scenario calculators should show profit sensitivity when price/kg drops, because small price changes can require many more pigs/month.
- Avoid building a system that optimizes volume while silently destroying margin.

Owner comments:

- Pending.

#### 13. Membership And Community Potential

Planning suggestion:

- Keep loyalty quiet and relationship-led rather than discount-led.

Advisor/partner response:

- The future value may become the membership/community feeling around the farm.
- This can later connect subscriptions, priority access, seasonal boxes, experiences, accommodation, and other farm products.

Codex comment:

- This is not a pilot feature, but it should influence customer data design.
- Customer profiles should eventually support loyalty status, founding customer status, preferences, order history, feedback, and priority access.
- Do not start with a complex subscription system until fulfillment is stable.

Owner comments:

- Pending.

### Open Planning Questions From This Discussion

- Should Pilot V1 be half carcass only, or should full carcass remain available manually for known customers?
- What is the first price/kg that protects margin while still feeling fair?
- What deposit rule is non-negotiable before slaughter booking?
- Which legal slaughter facility and butcher can handle the first pilot without exposing the full customer strategy?
- What exact cold-chain checks are practical with current equipment?
- What is the maximum safe weekly capacity for the first 4 weeks?
- What customer message should be used if yield is lower than expected?
- Which towns are Zone 1 for the pilot?
- What information must appear on a label before the first sale?
- What data must be tracked manually first before the system automates it?

## Strategic Summary

The target model is:

> Pre-sold, legally slaughtered, professionally cut, personally delivered premium pork.

Amadeus should not compete as cheap pork.

Amadeus should compete on trust, sustainability, traceability, relationship, honest farming, personal service, clean systems, and consistent quality.
