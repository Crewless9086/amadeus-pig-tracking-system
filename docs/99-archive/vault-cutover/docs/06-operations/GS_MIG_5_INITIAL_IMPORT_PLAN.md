# GS-MIG-5 Initial Import Plan

Date: 2026-06-29

Branch: `gs-mig-5-initial-import-plan`

Mode: controlled initial import plan after additive schema apply. No Supabase data import, Google Sheets write, app cutover, customer send, public post, payment, reservation, or lifecycle/purpose write was performed in this phase.

## Current State

GS-MIG-4 applied the additive canonical farm schema. The new Supabase tables/views exist and were verified empty.

The owner cleaned some `WEIGHT_LOG` rows in Google Sheets before this phase. A fresh read-only verifier was run against the current sheet data.

## Fresh Read-Only Verifier Result

Command:

```powershell
.\venv\Scripts\python.exe scripts\google_sheets_farm_import_dry_run.py --backfill-verifier --review-samples 20
```

Result:

- `success`: true
- `writes_to_supabase`: false
- `writes_to_sheets`: false
- `mode`: `dry_run_policy_backfill_verifier`
- `verification.no_write_performed`: true
- `verification.import_ready`: false
- `verification.pending_review_count`: 9

## Key Improvement Since GS-MIG-4

Missing-`Pig_ID` weight rows are now resolved in the current Google Sheets data.

Before owner cleanup:

- 6 quarantined missing-`Pig_ID` weight rows

After owner cleanup:

- 0 quarantined missing-`Pig_ID` weight rows

Remaining blocker:

- 9 conflicting same-pig/same-date weight groups

## Current Canonical Payload Counts

| Target table | Original mapped rows | Canonical policy rows |
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

## Current Review Output

Review items: 35 total.

| Review type | Count | Status |
| --- | ---: | --- |
| `same_weight_duplicate` | 25 | `auto_resolved_dedupe` |
| `same_movement_duplicate` | 1 | `auto_resolved_dedupe` |
| `conflicting_weight` | 9 | `pending_owner_review` |

Pending owner/admin review items before full import readiness: 9.

## Proposed Initial Import Decision

Recommended initial import approach:

1. Import all clean canonical payloads.
2. Import same-weight duplicate groups as one canonical event each, preserving source references.
3. Import repeated movement duplicate group as one canonical movement, preserving source references.
4. Exclude the 9 conflicting-weight groups from canonical import for now.
5. Produce a conflict review artifact listing the 9 pending groups.
6. Do not let the 9 conflicts affect current weight, allocation, meat readiness, or stock valuation until resolved.

This lets the farm move forward with the clean data while keeping questionable rows visible and controlled.

## Required Import Safety Rules

The initial import must:

- be idempotent
- run inside a transaction or clearly ordered retry-safe batches
- write only to the GS-MIG canonical farm tables
- not write to Google Sheets
- not cut over app reads/writes
- not touch customer sends, public posts, payments, reservations, or lifecycle/purpose writes
- preserve source sheet row/source id traceability
- produce row counts before and after import
- prove imported counts match the verifier counts
- leave conflicting weights visible in review output

## Import Order

Use this order to satisfy foreign keys:

1. `pens`
2. `pigs`
3. `farm_products`
4. `app_settings`
5. `litters`
6. `mating_events`
7. `pig_weight_events`
8. `pig_location_events`
9. `pig_medical_events`

If a foreign-key issue appears, stop and report. Do not weaken constraints without approval.

## Validation After Import

After a controlled import, verify:

- `pigs`: 217
- `pens`: 20
- `farm_products`: 3
- `app_settings`: 18
- `litters`: 17
- `mating_events`: 15
- `pig_weight_events`: 1,190
- `pig_location_events`: 179
- `pig_medical_events`: 261
- review output still lists 9 conflicting weights
- `pig_current_state` returns rows
- no Google Sheets data changed

## Rollback

Because this is the first canonical import, rollback should be simple if import batch IDs are used:

1. Stop app cutover; no app routes should read these tables yet.
2. Delete only rows with the specific import batch id from canonical farm tables, in reverse dependency order.
3. Leave schema in place.
4. Re-run verifier and import after fixing the issue.

Rollback SQL must be reviewed before use.

## GO / NO-GO

GO for owner review of this initial import plan.

NO-GO for executing the import until the owner explicitly approves GS-MIG-5 import execution.

## Next Approval Needed

To proceed, owner should approve:

> Apply GS-MIG-5 controlled initial import: import clean canonical farm data into Supabase, exclude the 9 conflicting-weight groups into review output, do not cut over app routes.
