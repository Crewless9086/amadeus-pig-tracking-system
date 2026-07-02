# Meat Sales Rules

- EFT only.
- VAT registered, VAT number `4510286224`.
- Prices are VAT-inclusive.
- Standard carcass orders use 50% deposit of estimated VAT-inclusive total.
- Final invoice uses actual packed weight.
- POP is evidence only.
- Bank-confirmed money unlocks the next gate.
- Delivery remains `To be confirmed` until approved.
- Customer payment reference should stay short and stable, using the last six alphanumeric characters of the order/sale reference.

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
