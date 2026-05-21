# Farm Operating System Map

## Purpose

Phase 10A planning document.

This map defines how the Amadeus Farm system should fit together before Supabase migration or deeper workflow integrations start.

The goal is to avoid building new integrations on top of a Google Sheets structure that will later move to Supabase/Postgres.

## Current Recommendation

Use this order:

1. Map the operating system and data ownership.
2. Set up Supabase foundations.
3. Migrate one bounded data area at a time.
4. Update n8n and assistant workflows to call backend APIs rather than direct sheet reads/writes.

Do not start with a full Supabase migration before the system map is clear.

Do not build Phase 10 integrations directly on raw Google Sheets if those integrations are likely to move soon.

## System Principles

- Backend APIs own business rules and operational writes.
- AI agents interpret, summarize, and route; they do not own hidden data truth.
- n8n orchestrates workflows; it should not become the permanent data layer.
- Supabase/Postgres should become the durable transactional and telemetry data store where scale, history, and querying matter.
- Google Sheets can remain useful during migration for visibility, manual review, and temporary formula views.
- Sheets should be retired table by table only after web app replacement views are accepted.
- Hardware-control secrets must live in protected credentials or environment variables, not sheet cells or workflow expressions.

## Operating Modules

| Module | Current Surface | Current Data Owner | Target Data Owner | Phase 10 Notes |
| --- | --- | --- | --- | --- |
| Sales and orders | Sam, Chatwoot, web app, Oom Sakkie order lookup | Google Sheets via backend | Supabase via backend APIs | First migration boundary from Phase 7.2. |
| Order documents | Backend PDF generation, Google Drive, n8n delivery | Google Sheets metadata + Drive files | Supabase metadata + Drive/files | Keep backend as only document state owner. |
| Pig records | Web app pig pages and Google Sheets formulas | Google Sheets | Later Supabase phase | Do not migrate in first order phase unless pig data becomes the blocker. |
| Weights and reports | Web app weight entry/report/print sheets | Google Sheets | Later Supabase phase | Edit/void audit is deferred until Supabase. |
| Breeding and litters | Web app matings/litters | Google Sheets | Later Supabase phase | Keep stable while order migration happens. |
| Pork/meat business module | Planning document only | Not implemented | Future Supabase-backed module | Do not retrofit into current live-pig order flow quickly. |
| Weather | Oom Sakkie/weather workflows | Google Sheets/n8n | Supabase or backend read models if needed | Weather currently works; keep stable until telemetry review. |
| Sunsynk/power | Oom Sakkie Sunsynk workflow and alert workflow | Google Sheets/n8n | Likely Supabase telemetry + backend endpoints | Known slow path; needs dedicated telemetry review. |
| Irrigation | Oom Sakkie irrigation workflows | n8n/IFTTT/sheets | Backend-controlled hardware endpoints later | Secrets/env boundary must be cleaned before expansion. |
| Farm dashboard/home | Current web dashboard | Backend + Google Sheets | Backend APIs over mixed stores during migration | Build only after core contracts are clear. |

## Integration Boundaries

| Integration | Current Trigger | Current Reads | Current Writes | Target Rule |
| --- | --- | --- | --- | --- |
| Sam customer sales | Chatwoot webhook into `1.0` | Backend, sales stock sheets, conversation history | Backend order APIs, Chatwoot replies | Sam calls backend APIs only for data changes. |
| Oom Sakkie Telegram | GateKeeper Telegram trigger into `2.0` | Backend/order tools, weather/power tools | Telegram replies, callback workers | GateKeeper remains single Telegram trigger; tools should prefer backend APIs. |
| Backend order system | Flask routes | Google Sheets | Google Sheets, Drive, n8n webhooks | Add repository/data-access layer before migration. |
| Google Sheets | Manual/operator visibility and formulas | Backend/n8n/sheets formulas | Backend and selected n8n paths | Reduce direct workflow writes over time. |
| Supabase | Not yet connected | None | None | Introduce only after 10A map acceptance and 10.1 foundation setup. |
| n8n alerts | Scheduled/webhook workflows | Google Sheets and external APIs | Telegram/Chatwoot/sheets | Move heavy reads to backend endpoints where possible. |

## Data Ownership Register

| Data Area | Current Source Of Truth | Target Source Of Truth | Migration Priority | Notes |
| --- | --- | --- | --- | --- |
| `ORDER_MASTER` | Google Sheets | Supabase `orders` | 10.2 first boundary | Keep public order IDs. |
| `ORDER_LINES` | Google Sheets | Supabase `order_lines` | 10.2 first boundary | Preserve line price snapshots. |
| `ORDER_INTAKE_STATE` | Google Sheets | Supabase `order_intakes` | 10.2 first boundary | Keep intake-to-order links. |
| `ORDER_INTAKE_ITEMS` | Google Sheets | Supabase `order_intake_items` | 10.2 first boundary | Preserve item keys and match state. |
| `ORDER_DOCUMENTS` | Google Sheets | Supabase `order_documents` | 10.2 first boundary | Drive files can stay in Drive initially. |
| `ORDER_STATUS_LOG` | Google Sheets | Supabase `order_status_logs` | 10.2 first boundary | Required for audit and reports. |
| `SALES_PRICING` | Google Sheets | Supabase `sales_pricing` | 10.2 first boundary | Needs effective dates and admin page. |
| `PIG_MASTER` | Google Sheets | Later Supabase table | Later | Order completion still updates this during first migration. |
| `WEIGHT_LOG` | Google Sheets | Later Supabase table | Later | Needs audit-friendly edit/void model. |
| `MATING_LOG` / `LITTERS` | Google Sheets | Later Supabase tables | Later | Keep stable for now. |
| Weather logs | Google Sheets/n8n | Telemetry schema or backend read model | 10.3 review | Weather works now; avoid churn. |
| Sunsynk logs | Google Sheets/n8n | Telemetry schema + backend endpoints | 10.3 review | Known slow direct-agent path. |
| Irrigation actions | n8n/IFTTT | Backend command/audit endpoint | 10.3/10.5 | Hardware control must be auditable. |

## Phase 10A Deliverables

- Confirm this map covers the real system modules.
- Add missing workflows, sheets, backend routes, and external services.
- Mark each data area as: keep in Sheets, migrate first, migrate later, telemetry review, or retire.
- Identify every direct n8n-to-sheet write that should eventually move behind a backend API.
- Define which Supabase foundation tasks are needed before any data import.

## Phase 10.1 Supabase Foundation Gate

Detailed foundation plan:

- `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`

Do not import production data until these are decided:

- Supabase project URL and project reference.
- Render environment variable names for database connection.
- Migration tool and migration folder location in this repo.
- Local/dev versus production database policy.
- Backup and restore-test expectation.
- Whether service-role key is needed; if yes, backend-only.
- Whether anon key is needed; if yes, only after RLS policies are designed.
- Initial repository/data-access pattern.
- Rollback plan for first migrated read/write path.

## Open Questions

1. Should the first Supabase work include only order/sales transaction data, as Phase 7.2 recommends, or should telemetry move first because Sunsynk is already slow? Perhaps this is a good IDea to start with the Sunsynk data as this is slow, before I need to give you all the data and the sheet access to google so you can build th esame google sheet docs to ensure we have everything written down incase we need to circle back? Should we do this then rather a piece by piece? This might just iron out a few wrinkels whilst I understand the Supabase website.
 - With that how will n8n work with Supabase instead of google sheets?
 - Will we be able to do different sheets, like google sheet that will give better data or smalle chunks for the n8n LLM to read and answer?
 - What folders and Render file of data is needed to give you all in a spcefic folder on the laptop that runs the same way as this pig one how will we file it in here so it seperated but under the same files. VEry important to bring them all togther, There is Cron Jobs running an things like this to ensure data is logged every few minutes. 
 - Also need to understand the best way to make the data as best for the LLM to answer questions such as summaries for day, week, month, year, and total, and compare them and so forth. 
2. Should Google Sheets remain as read-only synced operator views during the first migration, or should replacement web views be built first and sheets retired faster?
3. Which Phase 10 dashboard widgets are essential for the first operating home page?
4. Which n8n workflows still write directly to sheets and need backend-owned replacements first?
5. Do we need a staging Supabase database before importing any real data?

## Owner Review Answer Captured

Current recommended answer to question 1:

- Use the shared Supabase foundation first.
- Keep orders/sales as the first migration boundary because those schemas and contracts are already the most mature.
- Do not ignore Sunsynk; move it into a dedicated telemetry review after the first database path is proven.
- Before changing the Sunsynk path, inventory its Google Sheets tabs, cron jobs, n8n workflows, Render/laptop scripts, data volumes, and read patterns so the new design is based on the real system.
- n8n should call backend endpoints once Supabase is involved. The backend should query Supabase and return small prepared JSON payloads.
- For LLM use, create small read models such as latest-state snapshots, daily summaries, hourly rollups, weekly/monthly rollups, and alert logs. Agents should not scan raw high-volume telemetry tables.
- Keep the related code in this repo under clear domain folders unless a separate runtime/deployment becomes necessary.

Staging answer:

- Use the existing Supabase Pro project as the foundation/staging workspace first because no live cutover happens during setup.
- Before importing real production data or switching live writes, decide whether that project stays production or a fresh production project is created.

## Phase 10.3 Telemetry Review

Detailed telemetry plan:

- `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`

10.3 has now been selected after the first Supabase order/sales path was proven and 10.2L4 was deployed-verified.

The priority is to inventory Sunsynk, weather, forecast, irrigation, and alert data before changing workflows. The slow `2.2 - Amadeus Sunsynk Sub-Agent` should be fixed by moving toward backend-prepared telemetry payloads, not by making the n8n agent scan more Google Sheets data.
