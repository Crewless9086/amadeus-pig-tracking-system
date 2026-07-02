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
