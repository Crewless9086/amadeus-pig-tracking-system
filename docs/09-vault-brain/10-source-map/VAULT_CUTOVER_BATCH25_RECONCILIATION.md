# Vault Cutover Batch 25 Reconciliation

Status: `COMPLETE / TEN BUSINESS-MODULE SOURCES ARCHIVED / FOCUSED CONTRACTS RETAINED`
Date: 2026-08-18
Baseline: `19e21ebcce73de2c51dcd21e9ddcc37242246b38`

## Scope And Result

Ten farm-calendar and meat/pork/SAM business-module documents were read and
reconciled. Durable calendar, production batch, commercial, cutting, payment,
campaign, customer-conversation, knowledge and allocation boundaries now live
only in focused Vault authority. Originals are preserved intact under
`docs/99-archive/vault-cutover/docs/08-business-modules/` and cannot steer new
missions.

## Current Authority Retained

- `08-business-rules/FARM_RULES.md` owns the farm-calendar contract.
- `03-business/MEAT_SALES.md`, the cutting/commercial standard and
  `08-business-rules/MEAT_SALES_RULES.md` own the offer and launch gates.
- `08-business-rules/MEAT_PRODUCTION_RULES.md` owns production evidence.
- The focused SAM and BEACON workflows own conversation and campaign behavior.
- `config/sam_farm_knowledge.json` remains runtime language configuration only;
  it cannot override focused rules or backend gates.

## Boundaries

- No document was deleted; all ten were archived intact.
- No customer send, public post, provider action, order, reservation, payment,
  stock, farm, database or runtime effect occurred.
- The remaining physical queue is 42 documents in Batches 26 and 27.
