# Data And Supabase Contracts

## Core Rule

Supabase is the operational truth where migration has been completed. Google Sheets is legacy/reference/export/fallback unless a route is explicitly still using it.

Markdown docs describe rules and operating context. They are not runtime collaboration state.

## Source-Of-Truth Responsibilities

| Layer | Responsibility |
| --- | --- |
| Flask backend | business logic, validation, safe writes |
| Supabase/Postgres | durable transactional/telemetry records where migrated |
| Google Sheets | legacy visibility, fallback, import/export, selected formula views |
| n8n | orchestration, not data ownership |
| AI agents | language reasoning, summaries, drafts, recommendations |
| Chatwoot | customer message transport |

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

## CHARLIE Vault Tables

CHARLIE's normalized Vault layer includes or targets tables for:

- mission projects;
- artifacts;
- agent runs;
- review board findings;
- owner decisions;
- income stream reviews;
- improvement proposals/evidence.

Mission metadata still carries important mission vault fields. Normalized Vault tables are the durable structured layer for cross-mission intelligence.

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

## Telemetry And LLM Read Models

Agents should not scan raw high-volume telemetry tables. They should read prepared payloads:

- latest state;
- daily summaries;
- hourly rollups;
- weekly/monthly rollups;
- alert logs;
- small owner-ready JSON.

## Source References

- `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`
- `docs/01-architecture/COMPONENT_OWNERSHIP.md`
- `docs/02-backend/DATA_MODELS.md`
- `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`
- `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`
- `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`
- `docs/03-google-sheets/WRITE_OWNERSHIP.md`
- `docs/04-n8n/WORKFLOW_RULES.md`
- `modules/charlie/vault_store.py`
