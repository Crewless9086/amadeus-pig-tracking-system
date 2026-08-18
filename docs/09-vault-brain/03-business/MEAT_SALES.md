# Meat Sales

Status: active money-first path under Amadeus Farm Sales.

Goal: controlled pilot that generates real demand, handles Chatwoot conversations cleanly, creates usable leads, supports owner review, and learns from every sales conversation.

## Strategic Model

Amadeus Farm meat sales is the first near-term income-stream proof for the agent system.

The target model is:

> Pre-sold, legally slaughtered, professionally cut, personally delivered premium pork.

The business must not compete with supermarkets on cheap price. It competes on trust, sustainability, traceability, relationship, clean communication, and consistent quality.

Core rule: no pig is slaughtered for meat sales unless it is pre-sold and the required deposit is bank-confirmed.

## Sales Streams

Meat Sales sits inside the wider Amadeus Farm Sales structure:

- live pig sales remain the current operational sales stream;
- slaughter/abattoir sales remain the fallback outlet for pigs that do not sell through the meat path in time;
- standard half/full carcass meat sales are the current premium growth lane;
- assisted slaughter and custom cuts are later add-ons once the standard model is stable.

SAM is the Farm Sales CEO. Specialist sales agents can later sit under SAM for meat sales, live pig sales, slaughter/abattoir sales, and butcher/custom-cut sales.

## Pilot Offer

Pilot V1 should stay simple:

- public pilot focus: half carcass;
- three standard half-carcass collections: Amadeus Signature, Ember, and Grand
  Cut;
- a full carcass contains two independently selected half-carcass collections,
  which may be the same or different;
- custom cuts stay later at a higher price and higher deposit;
- Zone 1 towns: Riversdale, Albertinia, Still Bay;
- first four weeks should be capped at 1 pig/week until the process is calm.

## Current Rules

- EFT only.
- VAT registered, VAT number `4510286224`.
- Prices are VAT-inclusive.
- Standard carcass orders use 50% deposit of estimated VAT-inclusive total.
- Custom cut orders should use 70% deposit when that lane opens.
- Final invoice uses actual packed weight.
- POP is evidence only; bank-confirmed money unlocks the next gate.
- Balance must clear before delivery.
- Delivery only; customer collection is not currently offered.
- Customer payment reference should stay short and stable, using the last six alphanumeric characters of the order/sale reference.

## Pricing Direction

Owner-confirmed pilot price:

- standard half/full carcass: `R130/kg` VAT-inclusive;
- custom processing later: around `R145-R150/kg`;
- older `R100/kg` planning is too risky once VAT, slaughter, butchery, packaging, delivery, and admin are included.

Margin protection rules still need final owner-approved thresholds:

- minimum acceptable profit per pig;
- minimum delivery profitability by zone;
- minimum order values;
- premium custom processing fees;
- emergency cost review thresholds.

## Product And Yield Assumptions

Preferred meat model slaughter target:

- around `60 kg` live weight;
- estimated carcass yield `43-45 kg`;
- estimated saleable packed meat `38–42 kg`;
- current planning assumption: `42 kg` saleable carcass weight per `60 kg` pig until farm data replaces it.

At `R130/kg`, the planning example is:

- `42 kg x R130 = R5,460` VAT-inclusive revenue;
- VAT-exclusive value about `R4,748`;
- estimated direct cost around `R2,600`;
- estimated clean profit around `R2,148` per pig.

The longer-term example target is about 24-25 meat pigs/month for a `R50,000` clean monthly contribution, but this must not be attempted until fulfilment is proven.

## Cut Sets

The authoritative cutting and commercial contract is
`AMADEUS_MEAT_CUTTING_AND_COMMERCIAL_STANDARD.md`.

- Set A: Amadeus Signature Collection;
- Set B: Amadeus Ember Collection;
- Set C: Amadeus Grand Cut Collection.

Set D is retired from new pilot offers. Historical Set D evidence remains
historical and must not be silently converted.

Each collection is one complete half-carcass cutting route. A full carcass may
use the same collection for both halves or a different collection per half.

Standard suitable cut pieces are packed four per pack; pork leg chops are
packed two per pack. Whole cuts remain complete. Stew meat is distributed
evenly across its applicable packs. Head, feet, offal, excess bones/fat/skin,
and other unlisted by-products are excluded from the current customer offer.

## Weekly Operating Rhythm

Suggested first rhythm:

- Monday: close orders, confirm deposits, finalize cut sets, allocate pigs;
- Tuesday/Wednesday: confirm slaughter bookings, prepare delivery schedule, print labels and customer notes;
- Thursday: pigs sent to legal slaughter facility;
- Friday: butchery/cutting/packing, final weights confirmed, final invoices issued;
- Saturday: local delivery.

Scaling rule:

- start with 1 pig/week;
- then 2 pigs/week;
- then 3 pigs/week;
- later target 6 pigs/week only after the process is stable.

## Customer Experience

Packaging must communicate sustainability, cleanliness, trust, personal care, and premium-but-not-fake luxury.

Each order should eventually include:

- proper meat label;
- product name;
- packed weight;
- pack date;
- freeze/use guidance;
- farm brand;
- batch/order number;
- simple sustainability message;
- personal thank-you card or farm postcard.

Loyalty must be quiet and relationship-led, not discount-led. Strong future loyalty is based on access, priority, being remembered, and consistent quality.

## Agent Structure

Agents: SAM as Farm Sales CEO, future Meat Sales Agent, Butcher, Ledger, Beacon, Oom Sakkie, Analyst.

## Source References

- `docs/09-vault-brain/03-business/AMADEUS_MEAT_CUTTING_AND_COMMERCIAL_STANDARD.md`
- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md`
- `docs/09-vault-brain/08-business-rules/MEAT_PRODUCTION_RULES.md`
