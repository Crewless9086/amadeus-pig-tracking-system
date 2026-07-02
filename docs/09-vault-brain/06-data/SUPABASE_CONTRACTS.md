# Supabase Contracts

Supabase is operational truth where migration has been completed. Backend APIs own business logic, validation, and safe writes.

Agents and n8n must not bypass backend business logic for operational writes.

## Source-Of-Truth Responsibilities

| Layer | Responsibility |
| --- | --- |
| Flask backend | Business logic, validation, safe writes |
| Supabase/Postgres | Durable transactional, operational, telemetry, and mission records where migrated |
| Google Sheets | Legacy visibility, fallback, import/export, and selected formula views |
| n8n | Orchestration, not data ownership |
| AI agents | Language reasoning, summaries, drafts, recommendations |
| Chatwoot | Customer message transport |

## Current Supabase-Migrated Areas

The active docs report Supabase canonical support for:

- pigs;
- pens;
- farm products;
- app settings;
- weight events;
- location events;
- medical events;
- litters;
- mating events;
- pig current/latest views;
- orders;
- order lines;
- order intakes;
- order documents;
- order status logs;
- sales pricing;
- sales transactions;
- telemetry/weather/power/irrigation rollups where implemented;
- CHARLIE mission queue;
- Beacon media/campaign evidence;
- meat sales learning evidence.

## Write Rules

No agent should write directly to Supabase or Google Sheets unless:

- the backend/service path is approved;
- the action is within the mission approval level;
- owner gates are satisfied;
- audit/event logging is included;
- tests verify success and failure modes.

n8n must not bypass backend business logic for operational writes.

## Migration Rules

Before any migration:

- confirm source and target ownership;
- run dry-run/reconciliation;
- define rollback;
- verify additive schema;
- apply only with explicit approval;
- record evidence and update Vault Brain.
