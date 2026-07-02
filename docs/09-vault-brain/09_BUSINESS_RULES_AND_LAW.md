# Business Rules And Legal Boundaries

## Purpose

This file captures current business and legal/safety boundaries known from the repo. It is not legal advice. Owner/legal review is required before treating any compliance section as final.

## Customer Communication Rules

Agents must not:

- invent availability;
- invent prices;
- promise delivery;
- confirm payment from POP alone;
- confirm final booking before approved backend gates pass;
- send customer messages outside approved Chatwoot/WhatsApp/service-window rules.

SAM may ask useful follow-up questions and prepare replies only inside configured backend gates.

## Meat Sales Rules

Current controlled meat path:

- EFT only for meat sales.
- Amadeus is VAT registered.
- VAT number: `4510286224`.
- Prices are VAT-inclusive.
- Standard carcass orders use 50% deposit of estimated VAT-inclusive total.
- Final invoice uses actual packed weight.
- POP is evidence only; bank-confirmed money unlocks the next gate.
- Delivery line remains `To be confirmed` until confirmed by approved process.
- Customer payment reference should stay short and stable, using the last six alphanumeric characters of the order/sale reference.

## Beacon Marketing Rules

Beacon must not:

- post publicly without owner-approved gates;
- spend money without approved cap and rules;
- use unapproved/private media;
- use sensitive people/customer/private-location media without approval;
- create demand that the farm cannot fulfil.

Public copy must not overpromise stock, timing, delivery, final booking, or price unless the backend and owner approval support it.

## Farm Record Rules

Farm lifecycle and animal records require approved backend paths and owner approval where needed. This includes:

- purpose changes;
- death/removal;
- movement;
- medical treatment;
- litter lifecycle;
- mating/breeding state;
- weight event imports/edits;
- slaughter exits.

## Payments And Finance

Agents must not:

- record payment as confirmed from POP alone;
- change prices autonomously;
- approve deposits or final balances;
- create financial records without approved rails;
- promise refunds/cancellations without approved policy.

## Privacy / POPIA / Media

Open items needing owner/legal review:

- POPIA privacy notice for customer data;
- retention rules for customer conversations and media;
- consent rules for public use of photos/videos;
- rules for images containing people, children, vehicles, license plates, or private locations;
- data deletion/export process;
- transport customer data rules for future FRED.

Existing external web privacy/terms files exist under `external_sources/web/amadeus-landing/`, but this Vault Brain does not yet treat them as reviewed legal policy.

## Private Transfers / FRED Legal Gaps

Before FRED can operate, define:

- legal operating entity and service terms;
- insurance and liability;
- driver/vehicle requirements;
- booking, cancellation, refund policy;
- passenger privacy and data handling;
- customer messaging and payment rules;
- emergency and incident SOP.

## Source References

- `docs/05-ai/RESPONSE_RULES.md`
- `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md`
- `docs/05-ai/agents/beacon/BEACON_SCOPE.md`
- `external_sources/web/amadeus-landing/privacy.txt`
- `external_sources/web/amadeus-landing/terms.txt`
