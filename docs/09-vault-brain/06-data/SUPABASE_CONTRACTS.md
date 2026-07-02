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

## Foundation Decisions

- Use plain SQL migrations in `supabase/migrations/`.
- Backend/Render uses `DATABASE_URL`; secrets remain in env vars only.
- Keep all Supabase access behind Flask/backend services unless a future RLS/browser design is approved.
- Service-role keys must never be exposed to browser, n8n, committed docs, screenshots, Telegram, WhatsApp, or Chatwoot.
- RLS is enabled on public tables with no broad anon/auth policies unless a future frontend auth design is approved.
- Google Sheets remains legacy/reference/fallback until each table/route is explicitly cut over.

## Import/Cutover Gates

Before production import or live route cutover:

- backup/restore expectation is accepted;
- import script has a dry-run mode;
- include/exclude rules are documented and repeatable;
- test data exclusions are explicit;
- shadow import is compared against source;
- read-only comparison passes;
- rollback plan is documented;
- operator replacement view is accepted where needed;
- Vault Brain source map and data docs are updated.

## Telemetry Rules

- Agents should read compact backend read models, not raw high-volume telemetry tables.
- Current/latest state must not scan history.
- Daily/monthly/yearly rollups should be built from raw or lower-level rollups with coverage/quality fields.
- Estimated kWh/Rand values must be marked estimated until confirmed Sunsynk energy counters or approved calculation rules exist.
- Irrigation command/control requires backend-owned command/audit records before automation expands.

## Source References

- `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`
- `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`
- `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`
- `supabase/migrations/README.md`
