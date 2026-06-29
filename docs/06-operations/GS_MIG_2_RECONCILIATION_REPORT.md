# GS-MIG-2 Reconciliation Report

Date: 2026-06-29

Branch: `gs-mig-2-reconciliation`

Mode: read-only reconciliation. No migration was applied. No Supabase writes, Google Sheets writes, production data rewrites, customer sends, public posts, payments, reservations, or lifecycle/purpose writes were performed.

## Scope

GS-MIG-2 strengthens the Google Sheets to Supabase migration evidence before any import or cutover.

It adds:

- excluded-row samples for owner/admin review
- source sheet row counts
- payload count reconciliation
- duplicate candidate checks
- required-field quality checks
- formula sheet count comparisons
- tests proving reconciliation output and no-write behavior

It does not:

- apply `supabase/migrations/202606290001_create_farm_canonical_tables.sql`
- import data into Supabase
- cut over app routes
- change Google Sheets
- change production behavior

## Live Read-Only Reconciliation Result

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
- `import_readiness.ready_for_import`: false
- `import_readiness.reason`: reconciliation-only owner review required before import

## Source Sheet Counts

| Sheet | Rows |
| --- | ---: |
| `PIG_MASTER` | 217 |
| `PEN_REGISTER` | 20 |
| `WEIGHT_LOG` | 1,241 |
| `LOCATION_HISTORY` | 185 |
| `MEDICAL_LOG` | 261 |
| `PRODUCT_REGISTER` | 3 |
| `LITTERS` | 17 |
| `MATING_LOG` | 15 |
| `SYSTEM_SETTINGS` | 18 |
| `PIG_OVERVIEW` | 217 |
| `SALES_AVAILABILITY` | 21 |
| `SALES_STOCK_DETAIL` | 21 |
| `SALES_STOCK_SUMMARY` | 21 |
| `SALES_STOCK_TOTALS` | 6 |
| `LITTER_OVERVIEW` | 17 |
| `MATING_OVERVIEW` | 15 |

## Proposed Payload Counts

| Target table | Rows |
| --- | ---: |
| `pigs` | 217 |
| `pens` | 20 |
| `pig_weight_events` | 1,235 |
| `pig_location_events` | 185 |
| `pig_medical_events` | 261 |
| `litters` | 17 |
| `mating_events` | 15 |
| `farm_products` | 3 |
| `app_settings` | 18 |

## Excluded Rows

`WEIGHT_LOG` has 6 excluded rows because `Pig_ID` is missing.

| Source row | Weight log id | Reason |
| ---: | --- | --- |
| 924 | `WGT-403521CE` | missing `Pig_ID` |
| 927 | `WGT-5A2B1215` | missing `Pig_ID` |
| 944 | `WGT-00CBE055` | missing `Pig_ID` |
| 946 | `WGT-99A8A4CF` | missing `Pig_ID` |
| 948 | `WGT-99DF83AD` | missing `Pig_ID` |
| 996 | `WGT-6F530790` | missing `Pig_ID` |

These rows must be reviewed before canonical import. They should not be guessed into a pig record.

## Duplicate Review Candidates

The reconciliation found no duplicate primary event IDs, but it did find business-key duplicates that need review before import:

- `pig_weight_events`: 34 same-pig/same-date weight duplicate keys.
- `pig_location_events`: 1 same-pig/same-date/same-to-pen movement duplicate key:
  - `PIG-2026-9613|2026-06-22|PEN-012`: 7 rows

These may be legitimate repeated entries, corrections, or duplicate artifacts. GS-MIG-3 should not write canonical data until the import process defines how to mark duplicates, corrections, and same-day replacement records.

## Formula Count Reconciliation

Direct count matches:

| Formula sheet | Formula rows | Target rows | Status |
| --- | ---: | ---: | --- |
| `PIG_OVERVIEW` | 217 | 217 | count match |
| `LITTER_OVERVIEW` | 17 | 17 | count match |
| `MATING_OVERVIEW` | 15 | 15 | count match |

Compare-only formula sheets:

| Formula sheet | Rows | Status |
| --- | ---: | --- |
| `SALES_AVAILABILITY` | 21 | no direct target table yet |
| `SALES_STOCK_DETAIL` | 21 | no direct target table yet |
| `SALES_STOCK_SUMMARY` | 21 | no direct target table yet |
| `SALES_STOCK_TOTALS` | 6 | no direct target table yet |

The sales formula sheets still need formula-equivalence tests before sales dashboard/meat planning can be cut over.

## Field Quality Result

The mapped payloads have no required-field quality issues after excluding the 6 missing-`Pig_ID` weight rows.

## GS-MIG-2 Decision

GO for owner review of the reconciliation PR.

NO-GO for applying the migration or importing data until:

- the 6 missing-`Pig_ID` `WEIGHT_LOG` rows are reviewed
- same-pig/same-date weight duplicates are classified
- the repeated location movement key is classified
- formula-equivalence tests are designed for sales stock/readiness sheets
- owner approves GS-MIG-3

## Recommended GS-MIG-3

GS-MIG-3 should remain controlled and staged:

1. Apply the additive schema only after owner approval.
2. Build a dry-run backfill verifier that compares import payloads against empty canonical tables or staging tables.
3. Add duplicate classification rules before any write.
4. Build formula-equivalence tests for `PIG_OVERVIEW`, `LITTER_OVERVIEW`, `MATING_OVERVIEW`, and sales stock sheets.
5. Do not cut over app routes until the reconciliation report is clean.

## Tests Run

Passed:

- `.\venv\Scripts\python.exe -m unittest tests.test_google_sheets_farm_import_dry_run`
- `.\venv\Scripts\python.exe -m unittest tests.test_pig_weights_bulk_service`
- `.\venv\Scripts\python.exe -m py_compile scripts\google_sheets_farm_import_dry_run.py`

Safety checks:

- read-only live dry-run completed
- no migration applied
- no Supabase writes
- no Google Sheets writes
- no production behavior changes
