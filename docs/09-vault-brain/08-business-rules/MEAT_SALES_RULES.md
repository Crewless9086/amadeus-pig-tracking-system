# Meat Sales Rules

## Non-Negotiables

- SAM Meat is in fail-closed `interest_capture_only` mode until the owner proves the complete slaughter, abattoir, butcher, cuts, packing, pricing, cold-chain/quality, and exception loop and explicitly approves graduation.
- In this mode, SAM may capture structured meat interest and prepare owner-review reply wording only. Customer/document sends, actionable quotes, payment progression, reservations, bookings, butcher instructions, fulfilment, public launch, orders, stock changes, and farm lifecycle writes are blocked at server-side service boundaries.
- Missing, partial, malformed, stale, unavailable, or conflicting readiness evidence is not proof. Environment flags, owner authentication, pilot percentages, deposit state, or carcass assembly cannot independently unlock the mode.

- EFT only.
- VAT registered, VAT number `4510286224`.
- Prices are VAT-inclusive.
- Standard carcass orders use 50% deposit of estimated VAT-inclusive total.
- Custom cut orders use 70% deposit when that lane opens.
- Final invoice uses actual packed weight.
- POP is evidence only.
- Bank-confirmed money unlocks the next gate.
- Balance must clear before delivery.
- Delivery remains `To be confirmed` until approved.
- Public meat sales are delivery-first. Collection is not a normal public option because there is no collection point yet; any collection exception requires owner approval.
- Customer payment reference should stay short and stable, using the last six alphanumeric characters of the order/sale reference.
- No pig is slaughtered for meat sales unless it is pre-sold and the required deposit is bank-confirmed.
- Public pilot should start with half carcass / Set A only, with full carcass allowed as manual override for trusted known customers.
- Meat Sales must not compete on supermarket price. It competes on trust, quality, traceability, relationship, and controlled availability.

## Launch Capacity Rules

- Pilot Zone 1 is Riversdale, Albertinia, and Still Bay.
- First four weeks should cap at 1 pig/week.
- Do not expand routes, cut sets, or volume because one customer asks.
- Expansion requires repeated successful delivery cycles, cold-chain confidence, calm admin, and owner approval.
- First public/customer launch must stay blocked until WhatsApp template names, owner-approved Beacon media, exact channel approval, pilot cap, and bank-confirmed money gates are proven.
- A controlled first pilot may use owner-reviewed manual draft/direct outreach only; it must not use automation, public posting, reservation, payment confirmation, fulfilment, or lifecycle writes until the matching backend gate passes.

## Pricing And Margin Rules

- Standard half/full carcass planning price is around `R130/kg` VAT-inclusive.
- Custom processing later should price around `R145-R150/kg`.
- Avoid launching too cheap and trying to raise pricing aggressively later.
- Margin calculators should eventually show how price/kg changes affect pigs/month, feed pressure, delivery load, and profitability.
- Needed final settings: minimum profit/pig, minimum delivery margin by zone, minimum order value, custom processing premium, and emergency cost-review threshold.

## Cold-Chain And Label Rules

- If cold-chain confidence is lost, product does not go out.
- Start with simple strict controls: cool boxes, frozen ice packs, sanitized delivery boxes, pack date tracking, same-day delivery where possible, limited route duration, and manual temperature checks.
- Minimum label fields: product name, packed weight, packing date, use/freeze guidance, batch/order ID, farm name, and storage instructions.
- Do not over-design labels before the first sales cycle. Clarity and traceability come first.

## Agent Boundaries

SAM may collect facts and prepare wording inside configured gates.

SAM, Beacon, Butcher, and Ledger must not:

- invent availability;
- invent prices;
- promise delivery;
- confirm payment from POP alone;
- confirm final booking before approved backend gates pass;
- create financial records without approved rails.

## Fulfilment Boundaries

Butcher may recommend matches and warn about overbooking. It cannot book slaughter, allocate carcasses, reserve stock, or confirm fulfilment alone.

## Source References

- `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md`
- `docs/08-business-modules/PORK_SALES_MODEL.md`
- `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`
