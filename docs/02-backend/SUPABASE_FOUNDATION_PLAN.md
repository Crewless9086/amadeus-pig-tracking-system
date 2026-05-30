# Supabase Foundation Plan

## Purpose

Phase 10.1 planning document.

This document defines what must be in place before Amadeus Farm starts moving operational data from Google Sheets into Supabase/Postgres.

This is a foundation plan, not a production cutover plan.

## Current Recommendation

Start with the shared Supabase foundation, then choose the first bounded migration:

1. Supabase foundation setup.
2. Repository/data-access pattern in the backend.
3. Empty schema migrations.
4. Read-only import/shadow checks.
5. First production cutover only after comparison and rollback gates pass.

For the first data boundary, the current recommendation remains:

- first: orders/sales transaction data
- separate fast-follow planning: Sunsynk/weather/irrigation telemetry

Reason:

- Orders/sales already have the most complete schema planning from Phase 7.2.
- Telemetry is high-volume time-series data and needs a different schema and query design.
- The same Supabase foundation supports both, so we do not lose time by setting up the shared foundation first.

## What Is Needed From Owner

Do not paste secrets into chat unless explicitly asked and safe. Prefer adding secrets directly to Render when instructed.

## Project Details Captured

Captured from owner screenshot on 2026-05-20:

| Field | Value |
| --- | --- |
| Project name | Amadeus Systems |
| Project ref | `cmosbfsrygohromzapxs` |
| Project URL | `https://cmosbfsrygohromzapxs.supabase.co` |
| Plan | Pro |
| Status | Healthy |
| Region | West EU (Ireland), `eu-west-1` |
| Compute | Micro / `t4g.micro` |
| Last backup seen | 19 hours ago |
| Last migration | No migrations yet |
| GitHub integration | No repository connected |

No database password, service-role key, anon key, or connection string has been captured in the repo.

Backup page check from owner screenshot on 2026-05-20:

- Scheduled database backups are available.
- Visible physical backups:
  - `2026-05-20 01:26:24 (+0000)`
  - `2026-05-19 01:31:43 (+0000)`
  - `2026-05-18 13:49:54 (+0000)`
- Supabase warning noted: database backups do not include Storage API objects, only database metadata about those objects.
- Point-in-time recovery is available as a Pro Plan add-on but is not currently enabled.

Current backup recommendation:

- Scheduled physical backups are enough for the no-cutover foundation phase.
- Do not enable the PITR add-on yet unless the owner accepts the extra cost and we are near real production data import or live write cutover.
- Revisit PITR before any table becomes the live production source of truth.

Needed when setup begins:

| Item | Needed For | Safe Handling |
| --- | --- | --- |
| Supabase project URL | backend config and future API references | Can be shared if needed; not secret. |
| Supabase project reference ID | project identification and docs | Can be shared if needed; not secret. |
| Region | latency and backup planning | Can be shared. |
| Database connection string | backend server connection | Store in Render env var only. |
| Database password custody | recovery and rotation | Owner-controlled; do not commit. |
| Backup/PITR status | restore planning | Document setting only. |
| Dev/staging decision | safe testing | Decide before imports. |
| Service-role key | only if backend admin path needs it | Backend-only env var; never browser. |
| Anon key | future browser/RLS use only | Do not use until RLS policies are planned. |

## Proposed Environment Variables

Backend/server only:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_PROJECT_REF`
- `SUPABASE_SERVICE_ROLE_KEY` only if a backend-admin feature truly needs it

Not for first slice:

- browser-side Supabase anon key
- n8n direct database credentials

## Render Environment Variable Plan

Add these to Render only when the backend implementation is ready to be tested against Supabase:

| Env Var | Required Now? | Value Source | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | Yes for deployed DB health test | Supabase database connection string | Secret. Add directly in Render. Do not paste into chat or commit. |
| `SUPABASE_URL` | Yes | Project URL: `https://cmosbfsrygohromzapxs.supabase.co` | Not secret, but keep it in env for consistency. |
| `SUPABASE_PROJECT_REF` | Yes | Project ref: `cmosbfsrygohromzapxs` | Not secret. Useful for diagnostics/docs. |
| `SUPABASE_SERVICE_ROLE_KEY` | No | Supabase API settings | Do not add until a backend admin feature requires it. |
| `SUPABASE_ANON_KEY` | No | Supabase API settings | Do not use until frontend/RLS policy planning exists. |

Render setup rule:

- Add `DATABASE_URL` manually in Render from the Supabase connection string.
- Never send `DATABASE_URL` through Telegram, WhatsApp, Chatwoot, n8n notes, screenshots, or committed docs.
- After adding `DATABASE_URL`, deploy and test `/health/database`.

## Local `.env` Plan

Local development may use a `.env` file, but `.env` is ignored by git and must remain uncommitted.

Expected local keys when database testing starts:

```text
DATABASE_URL=postgresql://...
SUPABASE_URL=https://cmosbfsrygohromzapxs.supabase.co
SUPABASE_PROJECT_REF=cmosbfsrygohromzapxs
```

Do not add service-role or anon keys locally unless a later phase explicitly needs them.

## Security Rules

- Backend is the only writer during the first database phase.
- n8n must call backend APIs, not write directly to Supabase.
- Browser/frontend must not call Supabase directly until Row Level Security policies are designed.
- Service-role key must never be exposed to the browser or n8n.
- Google Sheets remains the current source of truth until a specific table is cut over.
- No production import until backup and rollback gates are documented.

## Migration Tooling Decision

Decision for the first foundation slice:

- Keep plain SQL migration files in `supabase/migrations/`.
- Apply the first migrations manually through the Supabase SQL Editor or Supabase CLI during guided setup.
- Do not add Alembic or an ORM migration tool yet.
- Add a lightweight backend connection test before adding business tables.

Reason:

- Plain SQL is easiest to inspect, copy, review, and run while the project is still mostly Flask plus Google Sheets.
- Supabase is Postgres underneath, so SQL migrations are not throwaway work.
- Alembic can be reconsidered later only if we adopt SQLAlchemy models or the schema becomes too complex to manage with checked-in SQL files.

Owner note captured:

- Owner has not used these tools before and wants the safest practical default. Current default is therefore plain SQL first, guided step by step.

## Phase 10.1B Baseline Migration

Purpose:

- prove checked-in SQL migration review and execution before creating any business tables
- give the backend a harmless table to verify that the baseline SQL was applied
- avoid touching orders, pigs, weights, breeding, weather, Sunsynk, irrigation, or customer data

Migration file:

- `supabase/migrations/202605210001_foundation_migration_log.sql`

What it creates:

- schema: `app_private`
- internal table: `app_private.migration_log`
- one row with migration ID `202605210001_foundation_migration_log`

What it does not create:

- no order tables
- no pig tables
- no weight tables
- no breeding/litter tables
- no telemetry tables
- no customer-facing tables
- no data import

Manual run process:

1. Open Supabase SQL Editor.
2. Paste the full SQL from `supabase/migrations/202605210001_foundation_migration_log.sql`.
3. Run it once.
4. Deploy the backend that includes `GET /health/database/foundation`.
5. Test `/health/database/foundation`.

Expected result after SQL is applied:

```json
{
  "success": true,
  "configured": true,
  "status": "ok",
  "migration_id": "202605210001_foundation_migration_log"
}
```

Before the SQL is applied, `/health/database/foundation` should fail safely with `status = foundation_missing` or `foundation_check_failed`.

## Backend Pattern

Current backend code is tightly coupled to Google Sheets service calls.

Target pattern:

- service/business logic calls repository functions
- repository functions can read from Google Sheets or Supabase depending on the migration phase
- cutover happens per bounded data area, not all at once

First repository boundary should be orders/sales transactions:

- order headers
- order lines
- intakes
- documents
- status logs
- pricing

## First Migration Boundary

Use the Phase 7.2 order/sales boundary unless deliberately changed:

- `ORDER_MASTER` -> `orders`
- `ORDER_LINES` -> `order_lines`
- `ORDER_INTAKE_STATE` -> `order_intakes`
- `ORDER_INTAKE_ITEMS` -> `order_intake_items`
- `ORDER_DOCUMENTS` -> `order_documents`
- `ORDER_STATUS_LOG` -> `order_status_logs`
- `SALES_PRICING` -> `sales_pricing`

Detailed Phase 10.2 planning source:

- `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`

Phase 10.2A implementation state:

- Empty order/sales table migration prepared in `supabase/migrations/202605210002_create_order_sales_tables.sql`.
- Backend schema verifier prepared at `GET /health/database/order-schema`.
- Deployed verification passed on 2026-05-21: `/health/database/order-schema` confirmed all seven expected order/sales tables and no missing tables.
- No data import and no backend read/write cutover.

Do not migrate these in the first order boundary unless a separate decision is made:

- `PIG_MASTER`
- `WEIGHT_LOG`
- `MATING_LOG`
- `LITTERS`
- weather logs
- Sunsynk logs
- irrigation logs

## Telemetry / Sunsynk Planning Answer

Sunsynk is a real pain point and should not be ignored.

Recommended handling:

- Do not mix Sunsynk telemetry into the first order-data migration.
- Use the same Supabase foundation.
- Create a separate Phase 10.3 telemetry architecture review.
- Inventory all Sunsynk sheets, cron jobs, n8n workflows, Render services, scripts, and data volumes.
- Design telemetry tables for raw readings, rollups, and latest-state views.
- Let Oom Sakkie call a small backend endpoint such as "current power status" or "today power summary" instead of letting an agent scan large Google Sheets tabs.

## n8n With Supabase

Preferred target:

- n8n calls backend API endpoints.
- backend owns Supabase queries and business rules.
- n8n receives small, prepared JSON payloads.

Avoid:

- n8n writing directly to Supabase tables for operational data
- agents reading large raw Supabase ranges directly
- mixing workflow logic with data ownership

Acceptable later:

- n8n may call controlled backend endpoints that return focused read models:
  - current Sunsynk status
  - today's power summary
  - last 24-hour trend
  - weekly/monthly rollups
  - irrigation plan/action status

Owner decision captured:

- Use the backend to do the data work. n8n should call backend endpoints or pass the correct information to the backend.

## LLM-Friendly Data Shapes

For Oom Sakkie and Sam, raw data is usually the wrong shape.

Preferred data shape:

- latest-state snapshots for "now" questions
- daily summaries for "today"
- hourly rollups for "last 24 hours"
- daily rollups for week/month/year comparisons
- compact alert/event logs for exceptions
- explicit timestamps and freshness fields

For Sunsynk, likely read models:

- `power_current_status`
- `power_daily_summary`
- `power_hourly_rollup`
- `power_monthly_summary`
- `power_alerts`

The assistant should read these small summaries, not full raw logs.

Owner note captured:

- A similar summary approach already exists in the Google Sheets setup. Use that as a useful reference when the telemetry design starts.

## Repository / Folder Strategy

Keep the farm system together in this repo, but separate domains clearly:

Potential backend folders later:

- `modules/orders/`
- `modules/pig_weights/`
- `modules/farm_telemetry/`
- `modules/irrigation/`
- `modules/weather/`
- `modules/power/`
- `services/database_service.py`
- `repositories/` or domain-specific repository files

Potential docs:

- `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`
- `docs/02-backend/DATABASE_SCALING_PLAN.md`
- `docs/02-backend/TELEMETRY_DATA_PLAN.md`
- `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`

Do not create a separate laptop project for each farm subsystem unless deployment/runtime separation becomes necessary. Use clear folders under the same repo first.

Owner decision captured:

- Keep everything in this repo for now, with clean folders and clear domain boundaries.

## Guided Defaults

Because the owner has not used Supabase before, these defaults should be used unless deliberately changed:

- Use the existing Supabase Pro project as the foundation/staging workspace first, because no live production cutover happens during foundation setup.
- Before real production data is imported or live writes move to Supabase, decide whether that project stays production or whether a fresh production project is created.
- Use plain SQL migrations in `supabase/migrations/`.
- Keep all Supabase access behind the Flask backend.
- Do not let n8n or the frontend write directly to Supabase.
- Add a backend `/health/database` smoke endpoint during foundation setup.
- Migrate orders/sales first; review Sunsynk/weather/irrigation telemetry after the first database path is proven.

## Security Hardening Notes

2026-05-27 Supabase Security Advisor warning:

- Supabase reported `rls_disabled_in_public` for project `cmosbfsrygohromzapxs`.
- Cause: project tables were created through raw SQL migrations in the `public` schema, and RLS was not explicitly enabled.
- Official Supabase guidance is to enable Row-Level Security on public tables exposed through the Supabase Data API.
- Current Amadeus design keeps all Supabase access behind the Flask backend using `DATABASE_URL`; the browser should not read/write Supabase tables directly.
- Fix prepared in `supabase/migrations/202605270001_enable_rls_on_public_tables.sql`.
- The migration enables RLS on all current public tables and intentionally adds no anon/auth policies, leaving direct browser/Data API access closed by default.
- Do not add broad `anon` or `authenticated` policies unless a future frontend/Supabase Auth design is explicitly approved.
- Keep Google Sheets visible as read-only or synced operator views until the database-backed screens are proven.

2026-05-30 verification:

- Owner applied the RLS hardening migration.
- Supabase Security Advisor shows `0 errors` and `0 warnings`.
- Remaining `RLS Enabled No Policy` rows are informational suggestions and are expected for the current backend-only access model.
- Continue to avoid anon/auth policies until browser/Supabase Auth access is deliberately designed.

## `/health/database` Smoke Endpoint

Recommendation: add this during foundation setup.

Purpose:

- prove Render can connect to Supabase
- prove local development can connect when the local `.env` is configured
- give a quick deployment check before adding business tables

Rules:

- return only harmless status data, such as success, database time, and application version
- do not expose connection strings, passwords, service keys, table rows, customer data, or pig data
- keep it backend-owned and test it before any production data import

Implementation state:

- Added backend route `GET /health/database`.
- If `DATABASE_URL` is missing, the route returns `503` with `status = not_configured`.
- If configured and reachable, the route returns success plus harmless database status fields.
- The route must never return the connection string, password, service-role key, anon key, table data, customer data, or pig data.
- Local verification passed on 2026-05-21: focused database tests passed, full local unittest suite passed at 132 tests, and `/health/database` returned safe `503` / `not_configured` with no `DATABASE_URL`.
- Deployed verification passed on 2026-05-21: `/health/database` returned `success = true`, `status = ok`, `configured = true`, `database = postgres`, and harmless database UTC time.
- Phase 10.1B local baseline added: internal migration SQL plus backend `GET /health/database/foundation` verification endpoint. SQL has not yet been run in Supabase.
- Phase 10.1B local verification passed on 2026-05-21: focused database tests passed at 6 tests, full local unittest suite passed at 135 tests, and migration contract test confirms no business tables are created.
- Phase 10.1B deployed verification passed on 2026-05-21: owner ran the baseline SQL in Supabase SQL Editor and `/health/database/foundation` returned `success = true`, `status = ok`, migration ID `202605210001_foundation_migration_log`, and applied timestamp `2026-05-21T01:19:31.638474+00:00`.

## Setup Checklist

Before any code connects to Supabase:

- [x] Owner confirms first boundary: orders/sales first, telemetry later.
- [x] Use the existing Supabase Pro project as the foundation/staging workspace first; no production cutover yet.
- [x] Owner confirms Supabase backup/PITR status during guided setup: scheduled backups active; PITR available as add-on but not enabled.
- [x] Migration folder location: `supabase/migrations/`.
- [x] Migration execution method: plain SQL first, guided through Supabase SQL Editor or Supabase CLI.
- [x] Add env var names to Render plan.
- [x] Add local `.env` guidance without committing secrets.
- [x] Add backend database connection smoke test.
- [x] Confirm no frontend or n8n direct DB access.
- [x] Deployed backend can connect to Supabase through Render `DATABASE_URL`.

Before any production data import:

- [x] Baseline internal migration table created by manual SQL migration.
- [ ] Empty business tables created by future migrations.
- [ ] Import script can run in dry-run mode.
- [ ] Test-data exclusion rules are documented.
- [ ] Backup/restore plan is accepted.
- [ ] Read-only shadow comparison passes.
- [ ] Rollback plan is documented.

## Open Decisions

1. Render env vars: add only after owner is ready to configure secrets directly in Render.
2. Local `.env`: document exact keys when implementation starts, without committing secrets.
3. Production project decision before cutover: keep the foundation project as production if clean, or create a fresh production project if needed.
4. PITR add-on decision before production cutover: scheduled backups are acceptable for foundation, but PITR should be reconsidered before live writes.
5. Telemetry detail plan: start after the first order-table database path is proven.
