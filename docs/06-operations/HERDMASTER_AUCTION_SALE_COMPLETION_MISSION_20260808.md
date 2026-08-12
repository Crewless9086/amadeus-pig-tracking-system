# HERDMASTER Auction Sale Completion Mission

Status: owner-approved next HERDMASTER business mission after ROOTLINE completes the active irrigation/readback outcome.

Priority: correct current herd, availability and August income truth before further breeding expansion. Preserve the source-ready breeding work and resume it after this bounded sale mission.

## Owner-reported sale

Charl reports that 18 slow-growing piglets were taken to auction and sold for a total invoice amount of R4,470.51.

Reported tag numbers:

- 84
- 51
- 92
- 93
- 94
- 95
- 97
- 99
- 100
- 101
- 113
- 116
- 120
- 121
- 122
- 66
- 68
- 74

No sale, income, payment, allocation or lifecycle mutation is authorized merely by this document. The exact preview must be confirmed before production writes.

## Authoritative BKB invoice evidence

Charl supplied the original one-page BKB seller settlement tax invoice at
`external_sources/Auction_Invoice_S-EE02-2710.pdf`. Treat the document as private
financial evidence and do not expose its banking, contact or tax identifiers in
family messages or general logs.

The invoice proves:

- auction company: BKB;
- auction location: Riversdal;
- effective sale/exit date: 2026-08-05;
- invoice/reference: `S-EE02-2710`;
- 18 piglets sold in two lots;
- lot V10: 8 piglets at R260.00 each excluding VAT;
- lot V11: 10 piglets at R210.00 each excluding VAT;
- gross livestock revenue: R4,180.00 excluding VAT;
- output VAT: R627.00;
- gross invoice value: R4,807.00 including VAT;
- auction commission: R292.60 excluding VAT;
- VAT on commission: R43.89;
- total commission deduction: R336.49 including VAT;
- other expenses: R0.00;
- net settlement payable: R4,470.51;
- settlement method stated by BKB: EFT.

The invoice proves a net amount payable, not authoritative bank receipt. Actual
money received remains unconfirmed until reconciled against bank/payment
evidence. The owner reports that BKB normally settles during the week following
the auction; this is an expected timing window, not proof of payment. Buyer identity
and individual tag-to-lot membership are not supplied. Charl cannot determine which
eight tags belonged to V10 or which ten belonged to V11. Preserve that membership as
permanently Unknown, do not infer it and do not ask for it again.

For a VAT-aware monthly projection, preserve revenue, output VAT, commission
expense, commission input VAT and net settlement separately. Do not record only
R4,470.51 as gross income.

## Current system gap

The Riversdale Auction List is a pre-sale shortlist only. It does not record a completed sale, income, payment or pig exit. The generic sales transaction model recognises `Livestock`, `Slaughter` and `Meat`, but its direct create path currently supports only `Slaughter`. `Auction` is not a valid sale stream. Livestock order completion can mark pigs Sold/off-farm, but it is not a correct retrospective auction-lot intake when no ordinary customer order or per-pig price breakdown exists.

The invoice supplies a group total. Individual pig proceeds must remain Unknown unless the invoice or other attributable evidence provides a breakdown. The system must not divide R4,470.51 equally and present manufactured per-pig sale prices.

## Business outcome

One natural Oom Sakkie auction-sale report plus invoice evidence produces one consolidated preview. After Charl confirms that exact preview, the system records one Livestock/Auction sale, links the 18 canonical pigs, records the exact supported August income/payment facts, marks the pigs Sold and off-farm exactly once, refreshes every affected projection and closes visibly.

## Ownership

- Oom Sakkie is the ordinary owner interface and retains conversational context.
- HERDMASTER resolves the 18 tags, reconciles canonical animal/lifecycle truth, validates exit eligibility and refreshes herd projections.
- SAM Livestock/order-sales services own the governed livestock sale transaction boundary.
- Ledger/payment evidence owns whether money is merely invoiced, due, or actually received.
- No specialist creates a duplicate writer, auction database or Telegram route.

## Required discovery and preview

1. Bind the authenticated owner report and invoice without exposing private document data unnecessarily.
2. Resolve every reported tag uniquely to one canonical Pig ID.
3. Show one preview containing, for every animal:
   - tag and Pig ID;
   - current status, on-farm state and pen;
   - current purpose/availability;
   - reservation, order, allocation and prior-sale conflicts;
   - whether a completed auction exit is supported.
4. Reconcile the current Auction List, but do not require historical shortlist membership as proof of sale.
5. Do not ask again for the sale date, auction company/location, invoice reference,
   gross value, VAT, commission, net payable amount or stated EFT settlement method;
   the BKB invoice proves them. Ask at most one grouped question only if completion
   genuinely requires whether the R4,470.51 EFT has actually reached the bank account.
   Do not ask before the ordinary following-week settlement window unless conflicting
   payment evidence requires attention. Unknown tag-to-lot membership must not be asked
   again and must not block the overall 18-pig sale.
6. Display all proposed sale, financial, lifecycle, availability, movement and projection effects before confirmation.

## Transaction design

The generic sale contract must support:

- `sale_stream = Livestock`;
- an explicit Auction channel/subtype rather than inventing a new incompatible stream;
- gross revenue R4,180.00 excluding VAT and R4,807.00 including VAT;
- output VAT R627.00;
- commission expense R292.60 excluding VAT and R336.49 including VAT;
- commission input VAT R43.89;
- other expenses R0.00;
- net settlement payable R4,470.51;
- one invoice reference and evidence binding;
- 18 linked pig items;
- nullable/Unknown individual proceeds when only a lot total exists;
- exact transaction arithmetic without manufactured equal allocations;
- explicit payment state separate from invoiced revenue;
- duplicate-pig and duplicate-invoice prevention;
- deterministic preview/confirmation/replay identity.

Do not disguise the auction as Slaughter, do not manufacture a normal customer order, and do not insert a zero or equal line price merely to satisfy the old validator.

## Confirmed write outcome

Only after exact owner confirmation, perform one atomic operation or roll back everything:

1. Create one auction-channel Livestock sales transaction.
2. Link all 18 canonical Pig IDs once.
3. Record the invoice arithmetic in distinct supported fields: R4,180.00 revenue
   excluding VAT, R627.00 output VAT, R292.60 commission expense excluding VAT,
   R43.89 commission input VAT, R336.49 commission including VAT, R0.00 other
   expenses and R4,470.51 net settlement payable.
4. Record the August sale/receivable without claiming bank receipt unless separate
   payment evidence proves the EFT arrived.
5. Mark each supported animal `Sold`.
6. Set `On_Farm = No`.
7. Record the real exit date.
8. Record `Exit_Reason = Auction Sale` or the canonical equivalent preserving the Auction channel.
9. Link every exit to the sale and invoice.
10. Remove the pigs from current availability, sale stock, breeding, weighing, allocation and on-farm herd projections.
11. Close or supersede matching Auction List entries while preserving list history.
12. Refresh monthly livestock income, sales counts and herd totals.
13. Preserve every animal's prior history.

If any animal is dead, already sold/off-farm, reserved, linked to another non-cancelled transaction, duplicated or unresolved, fail the whole confirmation before writes and show the exact conflict. Charl may then approve an explicitly corrected set; the system must not silently record a partial 17-of-18 sale.

## Agentic acceptance

- Charl can report the sale naturally in English or Afrikaans and attach the invoice.
- Known tags, provider time and invoice facts are not requested again.
- One contextual question covers only genuinely missing sale facts.
- One human-readable preview shows all 18 animals and the exact R4,470.51 treatment.
- One protected confirmation performs the complete atomic outcome.
- Replay creates zero additional transactions, items, exits, income, messages or projection changes.
- Oom Sakkie returns one concise completion showing animals exited, sale/income state, payment state and any genuine follow-up.
- The app provides a visible completed auction-sale record and linked animal history.
- Unrelated herd, ROOTLINE, customers, orders and farm state remain unchanged.

## Stop condition

Business-complete means the real auction sale is recorded once, the supported 18 pigs no longer appear on farm, August livestock income reflects the exact supported R4,470.51 treatment, payment truth is explicit, projections reconcile and replay is zero-effect. Source, PR, deployment or a preview alone is not completion.
