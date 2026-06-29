# GS-MIG-1 Dry-Run Report

Date: 2026-06-29

Branch: `gs-mig-1-canonical-schema-dry-run`

Mode: schema proposal and read-only import dry-run tooling. No migration was applied. No Supabase writes, Google Sheets writes, production data rewrites, customer sends, public posts, payments, reservations, or lifecycle/purpose writes were performed.

## Scope

GS-MIG-1 adds:

- additive canonical farm schema proposal
- dry-run Google Sheets to Supabase mapper
- reconciliation/link issue summary
- unit tests proving dry-run/no-write behavior
- active-doc updates

It does not cut over app routes from Google Sheets to Supabase.

## Files Added

- `supabase/migrations/202606290001_create_farm_canonical_tables.sql`
- `scripts/google_sheets_farm_import_dry_run.py`
- `tests/test_google_sheets_farm_import_dry_run.py`
- `docs/06-operations/GS_MIG_1_DRY_RUN_REPORT.md`

## Files Updated

- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`
- `planning/ToDoList.md`
- `supabase/migrations/README.md`

## Schema Proposal Summary

The migration creates empty canonical tables:

- `pigs`
- `pens`
- `farm_products`
- `app_settings`
- `pig_weight_events`
- `pig_location_events`
- `pig_medical_events`
- `litters`
- `mating_events`

It also creates starter views:

- `pig_latest_weight_events`
- `pig_latest_location_events`
- `pig_current_state`

All new tables enable RLS and create no browser access policies. The backend remains the access layer.

## Live Read-Only Dry-Run Result

Command:

```powershell
.\venv\Scripts\python.exe scripts\google_sheets_farm_import_dry_run.py --summary-only
```

Result:

- `success`: true
- `mode`: dry_run_only
- `writes_to_supabase`: false
- `writes_to_sheets`: false
- `link_issues`: none

Payload summary:

| Target table | Rows |
| --- | ---: |
| `pigs` | 217 |
| `pens` | 20 |
| `pig_weight_events` | 1235 |
| `pig_location_events` | 185 |
| `pig_medical_events` | 261 |
| `litters` | 17 |
| `mating_events` | 15 |
| `farm_products` | 3 |
| `app_settings` | 18 |

Formula compare-only sheets:

| Sheet | Rows |
| --- | ---: |
| `PIG_OVERVIEW` | 217 |
| `SALES_AVAILABILITY` | 21 |
| `SALES_STOCK_DETAIL` | 21 |
| `SALES_STOCK_SUMMARY` | 21 |
| `SALES_STOCK_TOTALS` | 6 |
| `LITTER_OVERVIEW` | 17 |
| `MATING_OVERVIEW` | 15 |

Excluded/review rows:

- `WEIGHT_LOG`: 6 rows excluded because `Pig_ID` is missing.

## Tests Run

Passed:

- `.\venv\Scripts\python.exe -m unittest tests.test_google_sheets_farm_import_dry_run`
- `.\venv\Scripts\python.exe -m unittest tests.test_pig_weights_bulk_service`
- `.\venv\Scripts\python.exe -m py_compile scripts\google_sheets_farm_import_dry_run.py`
- destructive SQL grep for `drop table`, `truncate`, `delete from`, destructive `update public`, and `alter table ... drop`

The first live dry-run attempt without network approval failed at Google OAuth due local socket permission. The CLI now returns a safe JSON `sheet_read_failed` status for read failures instead of a traceback.

## Remaining Risks

- The migration has not been applied.
- No formula equivalence tests have been built yet.
- Six `WEIGHT_LOG` rows with missing `Pig_ID` need owner/admin review before canonical import.
- `pig_current_state` is only a starter view. It does not yet replace all `PIG_OVERVIEW` formulas.
- Sales readiness, stock summaries, and valuation are still compare-only.

## Recommendation

GO for owner review of GS-MIG-1 PR.

NO-GO for applying the migration or cutting over app routes until:

- owner approves the migration file
- the six missing `Pig_ID` weight rows are reviewed
- formula equivalence tests are built
- a GS-MIG-2 backfill/reconciliation phase is accepted
