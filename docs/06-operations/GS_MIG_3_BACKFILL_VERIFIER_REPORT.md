# GS-MIG-3 Backfill Verifier Report

Date: 2026-06-29

Branch: `gs-mig-3-review-backfill-verifier`

Mode: dry-run review/quarantine output and controlled backfill verification. No migration was applied. No Supabase writes, Google Sheets writes, production data rewrites, customer sends, public posts, payments, reservations, or lifecycle/purpose writes were performed.

## Scope

GS-MIG-3 turns the owner-approved import policies into deterministic dry-run output:

- missing `Pig_ID` weight rows become quarantine review items
- same-pig/same-date/same-weight duplicates collapse to one canonical weight event
- conflicting same-pig/same-date weights stay out of canonical import and become review items
- repeated same-pig/same-date/same-to-pen movements collapse to one canonical movement event
- source sheet rows and source IDs are preserved for traceability

It does not import data or cut over the app.

## Command

```powershell
.\venv\Scripts\python.exe scripts\google_sheets_farm_import_dry_run.py --backfill-verifier --review-samples 12
```

## Live Dry-Run Result

Result:

- `success`: true
- `mode`: `dry_run_policy_backfill_verifier`
- `writes_to_supabase`: false
- `writes_to_sheets`: false
- `policy_version`: `GS-MIG-3B-owner-approved`
- `verification.no_write_performed`: true
- `verification.import_ready`: false
- `verification.pending_review_count`: 15

## Canonical Payload Counts

| Target table | Original dry-run rows | Canonical policy rows |
| --- | ---: | ---: |
| `pigs` | 217 | 217 |
| `pens` | 20 | 20 |
| `pig_weight_events` | 1,235 | 1,190 |
| `pig_location_events` | 185 | 179 |
| `pig_medical_events` | 261 | 261 |
| `litters` | 17 | 17 |
| `mating_events` | 15 | 15 |
| `farm_products` | 3 | 3 |
| `app_settings` | 18 | 18 |

The reduction is intentional:

- duplicate same-weight rows collapse to one canonical event
- conflicting weights are excluded pending review
- missing-`Pig_ID` rows are quarantined
- repeated movements collapse to one canonical event

## Review / Quarantine Output

Total review items: 41.

| Review type | Count | Status |
| --- | ---: | --- |
| `missing_pig_id_weight` | 6 | `quarantined` |
| `same_weight_duplicate` | 25 | `auto_resolved_dedupe` |
| `conflicting_weight` | 9 | `pending_owner_review` |
| `same_movement_duplicate` | 1 | `auto_resolved_dedupe` |

Status totals:

| Status | Count |
| --- | ---: |
| `auto_resolved_dedupe` | 26 |
| `pending_owner_review` | 9 |
| `quarantined` | 6 |

Pending/quarantined items before import readiness: 15.

## Policy Verification

The verifier proves:

- missing `Pig_ID` rows are quarantined and not imported
- same-weight duplicates collapse to one canonical event
- conflicting weights are excluded until review
- duplicate movements collapse to one canonical movement
- source references are preserved
- no write is performed

## What The Owner Will Review Later

Conflicting weights will be presented as review items with:

- pig id
- weight date
- candidate weight values
- source sheet rows
- source `Weight_Log_ID` values
- selected canonical value blank until owner/admin decision

Until resolved, these rows must not affect:

- current weight
- meat readiness
- allocation
- stock valuation

## GO / NO-GO

GO for owner review of GS-MIG-3 PR.

NO-GO for production import/cutover until:

- the additive migration is explicitly approved and applied
- review/quarantine output is accepted
- owner/admin decides whether pending conflicts can remain excluded for initial import
- formula-equivalence tests are added for current-state and sales/readiness views

## Tests Run

Passed:

- `.\venv\Scripts\python.exe -m unittest tests.test_google_sheets_farm_import_dry_run`
- `.\venv\Scripts\python.exe -m unittest tests.test_pig_weights_bulk_service`
- `.\venv\Scripts\python.exe -m py_compile scripts\google_sheets_farm_import_dry_run.py`

Live read-only verifier:

- `.\venv\Scripts\python.exe scripts\google_sheets_farm_import_dry_run.py --backfill-verifier --review-samples 12`

Safety confirmation:

- no migration applied
- no Supabase writes
- no Google Sheets writes
- no customer sends
- no public posts
- no payments/deposits
- no reservations
- no lifecycle/purpose writes
