# GS-MIG-5 Initial Farm Data Import Execution Report

Date: 2026-06-29

## Status

Complete.

Clean canonical farm data was imported from Google Sheets into Supabase canonical farm tables using controlled tooling. No app routes have been cut over to the new tables yet.

## Import Batch

- Import batch id: `GS-MIG-5-2026-06-29`
- Source: Google Sheets read-only import payload
- Target: Supabase canonical farm tables
- Google Sheets writes: none
- App behavior changes: none
- Route cutover: none

## Safety Gates

- Canonical tables were verified empty before import.
- The import runner refused to import if canonical target tables already contained data.
- `LOCATION_HISTORY` source row accounting was tightened before execution so movement rows cannot be silently dropped.
- Conflicting same-pig/same-date weights were excluded from canonical import and remain pending owner/admin review.
- Same-weight duplicates were collapsed to one canonical event.
- Repeated movement duplicates were collapsed to one canonical movement where present.

## Imported Counts

| Table | Rows imported |
| --- | ---: |
| `pens` | 20 |
| `pigs` | 217 |
| `farm_products` | 3 |
| `app_settings` | 18 |
| `litters` | 17 |
| `mating_events` | 15 |
| `pig_weight_events` | 1,190 |
| `pig_location_events` | 179 |
| `pig_medical_events` | 261 |

## Post-Import View Counts

| View | Rows |
| --- | ---: |
| `pig_current_state` | 217 |
| `pig_latest_location_events` | 113 |
| `pig_latest_weight_events` | 155 |

## Review Items Held Out

- Total review items: 34
- Auto-resolved same-weight duplicates: 25
- Pending conflicting-weight groups: 9
- Missing-`Pig_ID` weight quarantine: 0 after owner cleanup
- Movement source rows accounted: 179 of 179
- Unaccounted movement source rows: 0

The 9 conflicting-weight groups were not imported and must not affect current weight, meat readiness, allocation, stock valuation, or dashboards until reviewed.

## Commands Run

- `.\venv\Scripts\python.exe -m unittest tests.test_google_sheets_farm_import_dry_run`
- `.\venv\Scripts\python.exe -m unittest tests.test_google_sheets_farm_import_execute`
- `.\venv\Scripts\python.exe -m py_compile scripts\google_sheets_farm_import_execute.py scripts\google_sheets_farm_import_dry_run.py`
- `.\venv\Scripts\python.exe scripts\google_sheets_farm_import_execute.py`
- `.\venv\Scripts\python.exe scripts\google_sheets_farm_import_execute.py --execute`
- Read-only post-import Supabase count checks

## Test Results

- `tests.test_google_sheets_farm_import_dry_run`: 16 passed
- `tests.test_google_sheets_farm_import_execute`: 3 passed
- Python compile check: passed
- Controlled import dry-run: passed
- Controlled import execute: passed
- Post-import count verification: passed

## No-Unsafe-Action Confirmation

- No Google Sheets writes were performed.
- No production records outside the approved canonical farm tables were changed.
- No app route reads were cut over.
- No customer sends, public posts, payments, deposits, reservations, or lifecycle/purpose writes were performed.
- No destructive SQL was run.
- No screenshots, external sources, assets, `.env`, `.claude`, or `planning/Prompts.md` were touched.

## Next Step

GS-MIG-6 should create the owner/admin review output for the 9 conflicting-weight groups and run controlled backfill verification against the imported Supabase rows before any route cutover.
