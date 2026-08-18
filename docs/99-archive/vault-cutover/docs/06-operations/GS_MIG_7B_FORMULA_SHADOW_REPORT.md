# GS-MIG-7B Formula Shadow Report

Date: 2026-06-29

## Status

Read-only formula shadow comparison completed. No app route cutover was made in this subphase.

## Safety

- No Google Sheets writes.
- No Supabase writes.
- No route behavior changes.
- No migrations.
- No customer sends, public posts, payments, reservations, lifecycle/purpose writes, Phase 3A.6, CHARLIE, FRED, or ledger work.

## Live Read-Only Result

Command:

```powershell
.\venv\Scripts\python.exe scripts\google_sheets_supabase_formula_shadow.py --json
```

Result:

- `PIG_OVERVIEW` row count matched Supabase `pig_current_state`: 217 vs 217.
- Active/on-farm count matched: 116 vs 116.
- Animal type counts matched:
  - Boar: 3
  - Finisher: 1
  - Grower: 40
  - Piglet: 87
  - Sow: 18
  - Weaner: 68
- Pig status counts matched:
  - Active: 116
  - Dead: 7
  - Died: 25
  - Slaughtered: 1
  - Sold: 68
- On-farm counts matched:
  - Yes: 116
  - No: 101
- `LITTER_OVERVIEW` row count matched Supabase `litters`: 17 vs 17.
- `MATING_OVERVIEW` row count matched Supabase `mating_events`: 15 vs 15.

## Not Equivalent Yet

These areas are still blocked for route cutover:

- `SALES_AVAILABILITY`
- `SALES_STOCK_SUMMARY`
- `SALES_STOCK_TOTALS`
- full `LITTER_OVERVIEW` attention/status logic
- dashboard litter attention
- pig allocation readiness
- meat planning

The script reports sales readiness and stock candidates as `not_implemented` because the Supabase replacement views/services are not built yet.

## Current Safe Cutover Boundary

Safe to continue with direct canonical farm reads from `pig_current_state`, `pigs`, `pens`, `farm_products`, `pig_weight_events`, `pig_location_events`, and `pig_medical_events`.

Not safe to switch sales stock/readiness or attention dashboards until the missing formula replacements exist and compare cleanly.

## Tests Run

- `python -m py_compile scripts/google_sheets_supabase_formula_shadow.py`
- `python -m unittest tests.test_google_sheets_supabase_formula_shadow`
- Existing GS-MIG-7A tests remained passing.

## Next

Build Supabase replacement services/views for:

1. Sales availability/readiness.
2. Sales stock summary/totals.
3. Litter overview attention.
4. Pig allocation readiness.
5. Meat planning.

Each replacement must have a shadow comparison before route cutover.
