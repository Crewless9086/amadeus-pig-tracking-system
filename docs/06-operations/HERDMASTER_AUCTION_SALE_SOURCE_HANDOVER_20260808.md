# HERDMASTER auction-sale source handover — 2026-08-08

Status: Prepared/source-only. No runtime, Telegram, customer, farm, order,
allocation, sales or accounting mutation occurred.

## BKB invoice-aware addendum — 2026-08-09

Private seller settlement evidence `S-EE02-2710` proves BKB, Riversdal,
sale/exit date 2026-08-05, eighteen piglets, gross livestock revenue R4,180.00
excluding VAT, output VAT R627.00, gross invoice value R4,807.00 including VAT,
commission R292.60 excluding VAT, commission input VAT R43.89, commission
R336.49 including VAT, other deductions R0.00, net settlement payable
R4,470.51, and stated method EFT. The private PDF is not source material and
must never be committed or exposed.

Payment received remains Unknown. The transaction records the August sale and
receivable independently; later attributable bank evidence updates the same
sale through an idempotent payment-reconciliation operation. Tag-to-lot
membership and all individual pig proceeds remain Unknown and do not block the
sale.

The preview contains the exact eighteen tag/Pig-ID mappings, all Sold/off-farm
effects, separate VAT and commission facts, settlement payable, Unknown receipt,
and no manufactured line prices. Its single optional grouped question is:
“Has the R4,470.51 EFT reached the bank account, and if known, which eight pigs
were in V10?”

Management-only analysis uses the 2026-08-03 recorded weights: combined 154.6
kg, average 8.59 kg, approximate gross including VAT per pig R267.06,
approximate net settlement per pig R248.36, and approximate net settlement per
recorded kilogram R28.92/kg. The invoice supplies no auction mass. No
continue-feeding/direct-sale recommendation is supported until attributable
feed-cost, growth-rate, direct-sale-value, and pen-capacity evidence exists.

## Canonical reconciliation

Read-only cutoff: 2026-08-08. All 18 tags resolve exactly once. Every row is
currently `Active`, on-farm, purpose `Sale`, pen `Skeer 003`, with no current
active outlet, open/non-cancelled order allocation, or prior sales item.
Canonical medical chronology has no withdrawal end later than 2026-07-20;
tag 51 also has an attributable owner review explicitly marked cleared. The
sanitized exact evidence fixture is
`tests/fixtures/herdmaster_auction_18_20260808.json`, SHA-256
`F182CED9F45D5633B0F3C18F63E492CC9A212F157F98B154F262E40D07FC0593`.

| Tag | Canonical Pig ID | Latest weight (2026-08-03) | Withdrawal evidence | Historical-sale inclusion |
|---:|---|---:|---|---|
| 84 | PIG-2026-B0BB | 10.8 kg | complete chronology; latest end 2026-04-27 | Supported |
| 51 | PIG-2026-04A0 | 10.0 kg | explicitly cleared; latest end 2026-04-06 | Supported |
| 92 | PIG-2026-DB07 | 7.6 kg | complete chronology; latest end 2026-05-05 | Supported |
| 93 | PIG-2026-B656 | 9.2 kg | complete chronology; latest end 2026-05-05 | Supported |
| 94 | PIG-2026-AC81 | 7.4 kg | complete chronology; latest end 2026-05-05 | Supported |
| 95 | PIG-2026-862A | 10.6 kg | complete chronology; latest end 2026-05-05 | Supported |
| 97 | PIG-2026-7CFC | 10.2 kg | complete chronology; latest end 2026-05-05 | Supported |
| 99 | PIG-2026-81B7 | 6.6 kg | complete chronology; latest end 2026-05-05 | Supported |
| 100 | PIG-2026-592A | 5.6 kg | complete chronology; latest end 2026-05-05 | Supported |
| 101 | PIG-2026-E46E | 6.6 kg | complete chronology; latest end 2026-06-09 | Supported |
| 113 | PIG-2026-9097 | 7.0 kg | complete chronology; latest end 2026-06-15 | Supported |
| 116 | PIG-2026-6577 | 6.0 kg | complete chronology; latest end 2026-07-20 | Supported |
| 120 | PIG-2026-CEF3 | 5.2 kg | complete chronology; latest end 2026-07-20 | Supported |
| 121 | PIG-2026-535A | 6.0 kg | complete chronology; latest end 2026-07-20 | Supported |
| 122 | PIG-2026-5C5C | 5.0 kg | complete chronology; latest end 2026-07-20 | Supported |
| 66 | PIG-2026-DF24 | 14.4 kg | complete chronology; latest end 2026-03-05 | Supported |
| 68 | PIG-2026-88DE | 14.2 kg | complete chronology; latest end 2026-04-06 | Supported |
| 74 | PIG-2026-1DC8 | 12.2 kg | complete chronology; latest end 2026-03-05 | Supported |

The owner report proves neither the auction/exit date nor the outlet/invoice
reference nor whether R4,470.51 is gross, net after fees, or money received.
Payment status is also Unknown. One grouped later question covers only those
facts. No individual price is inferred.

## Schema and source result

The pre-existing tables can retain nullable item prices but cannot correctly
distinguish a Livestock/Auction lot, preserve an authoritative lot total and
its financial interpretation, bind the confirmed preview/operation, or expose
received money separately. The existing direct create writer is deliberately
Slaughter-only. The additive migration supplies those exact fields without a
parallel ledger. Unknown gross, net, received and deductions amounts remain
NULL with explicit unknown counts in monthly reporting; they are never shown
as R0.00. The new service-only writer reuses `sales_transactions`,
`sales_transaction_items`, `pigs`, `pig_lifecycle_events`, and
`pig_active_outlets` in one transaction.

`/pig-allocation` remains prospective readiness only. No checkbox or shortlist
membership is required to record a genuine completed historical auction lot.

## Governed operation

The pure evaluator requires 18 unique canonical pigs and fails the entire lot
on identity, lifecycle, prior-sale, reservation/order, or withdrawal conflict.
The protected writer requires a trusted server-derived service principal,
exact owner-confirmed preview/operation/evidence identities, a durable
confirmation ID, unchanged evidence generation, serialized pig locks, and exact
current-state revalidation. It creates one sale, 18 nullable-price items and 18
append-only exit events; marks all 18 Sold/off-farm; and preserves historical
rows. Database outlet uniqueness plus the order-line current-pig guard closes
the concurrent reservation race. Only the sale's own outlet claims are
released; protected health, breeding and other claims are never cleared.
Replay returns zero rows.
Any mismatch or exception rolls back the entire transaction.

The existing authenticated Oom Sakkie intake must later call the pure preview
and show its allowlisted English/Afrikaans result. Shared registry/routing files
are intentionally untouched. After an explicit serialized release: integrate
PR #732 first, then review/integrate this separate PR, apply its migration,
verify exact lineage/health, send one natural owner preview, obtain one exact
confirmation, run the governed operation once, prove replay zero, reconcile
monthly `lot_total`/supported gross-net-received columns and active-herd counts,
and release immediately.
