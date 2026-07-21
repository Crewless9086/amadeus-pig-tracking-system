# Vault Brain Open Questions

Status: owner-reviewed governance questions were moved to `OWNER_DECISIONS.md`. This file now tracks only unresolved or verification-needed questions.

## Pig Lifecycle Audit Application And Capture

Question: before the additive lifecycle audit migration is applied or any protected event producer is built, which approved backend rail may emit each event type, which roles are valid actors, and what correction authorization/retention policy applies?

Known boundary: the additive, unapplied `pig_lifecycle_events` migration preserves immutable lifecycle evidence linked to canonical `pigs`. It has RLS, retry-safe idempotency, same-pig correction-by-supersession, requires every `lifecycle_correction` to supersede a prior event, prohibits supersession for other event types, and database-blocks updates/deletes. It does not change `pigs`, perform lifecycle actions, or expose detail/history reads.

Owner decision needed: explicitly approve migration application and the protected write/correction authority; approve the separate lifecycle-read/frontend work before exit/history visibility is changed.

## Pig Observation Capture And Retention

Question: before a protected observation-capture path is implemented, which farm roles may submit factual observations, what retention period applies, and who can authorize a correction event?

Known boundary: the additive, unapplied `pig_observation_events` migration stores factual pig evidence only. It has RLS, retry-safe idempotency, same-pig correction-by-supersession, and database-blocked updates/deletes. It stores no alert acknowledgement, recommendation, owner decision, notification, automation, lifecycle, medical, sales, reservation, or slaughter state.

Owner decision needed: approve the capture-role list, retention/deletion policy, and correction authorization before any protected backend capture rail is built or migration is applied.

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

## SAM Live Stock Sales Launch Settings

Question: which live-stock sales settings are approved before SAM Live Stock can move beyond routing/planning into runtime, customer replies, draft orders, reservations, or quotes?

Current working position:

- SAM Live Stock Stage 1/2 is allowed to define Vault authority and classify sales lane only.
- Backend writes, customer sends, draft orders, reservations, payment confirmation, and sales transaction writes are not approved yet.
- Current source truth must come from app/Supabase backend rails, not old n8n or Google Sheet truth.

Owner decisions still needed:

- confirm current live-stock price bands or approve a new active backend price source;
- confirm which categories are available for public sale first: piglets, weaners, growers, finishers, ready-for-slaughter live pigs;
- confirm whether SAM may create draft orders automatically later, or only owner-reviewed draft packets;
- confirm whether any live-stock reservation can ever be automatic, or must always be owner-gated;
- confirm first customer transport rule: buyer collection, farm delivery, or owner-arranged case by case;
- confirm rules for selling gilts, boars, sows, or any breeding/replacement-quality stock;
- confirm which WhatsApp/Chatwoot number/lane Live Stock Sales will use so it does not conflict with Meat Sales.

Source references:

- `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md`
- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`

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

## Repo Cleanup Review

Question: which active source buckets can be demoted after owner review?

Current recommendation:

- Keep `docs/02-backend`, `docs/03-google-sheets`, `docs/04-n8n`, and `docs/06-operations` as active technical/runtime references for now.
- Do not delete `docs/08-business-modules` until the owner accepts the Vault business docs as correct.
- Do not delete external sources until each source is explicitly marked keep/archive/delete.

Owner review needed:

- confirm whether `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md`, `PORK_SALES_MODEL.md`, and related campaign docs should remain active references after Vault business review;
- confirm whether old operation evidence logs should be compressed into monthly archive summaries;
- confirm whether external source folders are still needed locally or can be archived/deleted after useful context is captured.
