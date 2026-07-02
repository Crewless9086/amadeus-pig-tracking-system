# Vault Brain Open Questions

Status: owner-reviewed governance questions were moved to `OWNER_DECISIONS.md`. This file now tracks only unresolved or verification-needed questions.

## Supabase Vault Production Status

Question: which Supabase Vault tables are applied in production and which remain pending?

Known from repo:

- `supabase/migrations/202606300002_create_charlie_vault_v1_tables.sql` defines the first CHARLIE Vault v1 tables.
- `supabase/migrations/202607010002_create_charlie_core_v3_tables.sql` defines the expanded CHARLIE CORE v3 tables, including lessons and income-stream reviews.
- Runtime write-through services exist in `modules/charlie/vault_store.py`.

Still needs live verification:

- confirm which migration files have actually been applied in production Supabase;
- confirm `/api/charlie/core/vault-health` reports all expected tables healthy;
- confirm agent-run, handoff, owner-decision, audit, lesson, and income-stream review writes succeed in production.

## POPIA / Privacy Before Customer And Media Automation

Question: what POPIA/privacy docs are required before customer/media automation expands?

Working answer for owner review, not legal advice:

- privacy notice for customers and leads;
- lawful basis/consent rule for storing customer names, phone numbers, messages, order details, POP/payment evidence, delivery details, and media;
- direct marketing consent/opt-out rule for WhatsApp, SMS, email, Facebook, and future channels;
- media consent/public-use rule for photos or videos containing people, children, vehicles, license plates, private locations, customers, workers, or visitors;
- data retention rule for customer chats, POP evidence, order records, photos, videos, and campaign evidence;
- data access/correction/deletion request SOP;
- data breach/incident response SOP;
- Information Officer responsibility and registration status;
- third-party processor list for Supabase, Chatwoot, WhatsApp/Meta, n8n, Google, Telegram, hosting, and any marketing tools;
- cross-border data transfer rule if data is stored or processed outside South Africa.

Automation gate: no customer/media automation should expand until these rules exist at least as owner-approved internal policy, with legal review marked as pending where needed.

Source reference: Information Regulator South Africa says POPIA sets minimum conditions for lawful processing of personal information and the Regulator monitors and enforces POPIA compliance by public and private bodies.

## FRED / Private Transfers Compliance

Question: what legal/compliance docs are required before FRED/private transfers?

Current owner direction: start small and transition slowly while the insurance concept is being worked on.

Still needed before automation:

- service terms;
- booking and cancellation rules;
- payment/deposit/refund rules;
- driver/vehicle responsibility;
- insurance/liability position;
- passenger privacy/data handling;
- emergency/incident SOP;
- customer message rules;
- dispatch source-of-truth records.

Additional business decisions needed from the owner after Vault review:

- confirm whether the OMODA is the only Phase 1 vehicle;
- confirm the first public service area and whether Still Bay/Jongensfontein is included from day one;
- confirm whether route prices in `03-business/AMADEUS_PRIVATE_TRANSFERS.md` are approved launch prices or planning-only numbers;
- confirm the exact cancellation/refund rule before and after booking cutoff;
- confirm who may drive and whether each driver has or needs PrDP;
- confirm whether Amadeus Private Transfers gets a separate WhatsApp number before the first public test.

## Meat Sales Launch Settings

Question: which meat-sales settings are approved for the first real public sales cycle?

Working assumptions now captured in the Vault:

- Pilot V1 focuses publicly on half carcass / Set A;
- full carcass is manual override for trusted known customers;
- standard launch price direction is around `R130/kg` VAT-inclusive;
- custom processing later is around `R145-R150/kg`;
- standard carcass deposit is 50%;
- custom cut deposit is 70% once that lane opens;
- Zone 1 is Riversdale, Albertinia, and Still Bay;
- first four weeks are capped at 1 pig/week.

Still needs owner approval:

- exact first launch price/kg;
- exact delivery fee rules by town/zone;
- exact cancellation rule after slaughter booking;
- exact legal slaughter facility and butcher;
- exact cold-chain manual checklist for first deliveries;
- exact label wording and layout;
- exact minimum profit/pig and delivery-margin thresholds.

## Quartermaster / Farm Stock And Feed Control

Question: what exact farm stock, feed, natural resource, purchasing, expense, receipt, and stock-adjustment workflows should Quartermaster own?

Still needed before Quartermaster becomes active:

- feed categories and natural farm feed/resource list;
- stock item categories;
- purchase approval rules;
- expense capture rules;
- receipt storage rules;
- stock adjustment rules;
- stocktake frequency;
- dashboard placement;
- Supabase/source-of-truth tables;
- owner approval gates for purchases and stock changes.
