# GS-MIG-3A Data Issue Review

Date: 2026-06-29

Branch: `gs-mig-3a-data-issue-review`

Mode: read-only issue classification before any migration apply/import. No Supabase writes, Google Sheets writes, production data rewrites, customer sends, public posts, payments, reservations, or lifecycle/purpose writes were performed.

## Scope

GS-MIG-3A reviews the data-quality blockers found in GS-MIG-2:

- missing `Pig_ID` rows in `WEIGHT_LOG`
- same-pig/same-date duplicate weight groups
- repeated same-pig/same-date/same-to-pen movement groups
- owner decisions needed before canonical import

It does not:

- apply `supabase/migrations/202606290001_create_farm_canonical_tables.sql`
- import data into Supabase
- change Google Sheets
- cut over app routes
- alter production behavior

## Command

```powershell
.\venv\Scripts\python.exe scripts\google_sheets_farm_import_dry_run.py --issue-report
```

First attempt returned a safe no-write `sheet_read_failed` response due a transient Google transport error. The rerun with read-only Google access succeeded.

## Summary

| Issue | Count | Classification |
| --- | ---: | --- |
| Missing `Pig_ID` weight rows | 6 | Owner/admin must identify pig or exclude |
| Same-pig/same-date weight duplicate groups | 34 | 25 likely duplicates, 9 conflicting |
| Same-pig/same-date/same-to-pen movement duplicate groups | 1 | likely duplicate movement |

Import readiness remains `false`.

## Missing Pig ID Rows

These rows have a `Weight_Log_ID` but no `Pig_ID`; the diagnostic did not find enough context to infer the pig safely.

| Source row | Weight log id | Recommendation |
| ---: | --- | --- |
| 924 | `WGT-403521CE` | identify pig or exclude |
| 927 | `WGT-5A2B1215` | identify pig or exclude |
| 944 | `WGT-00CBE055` | identify pig or exclude |
| 946 | `WGT-99A8A4CF` | identify pig or exclude |
| 948 | `WGT-99DF83AD` | identify pig or exclude |
| 996 | `WGT-6F530790` | identify pig or exclude |

Recommendation: do not guess these. Either correct them in the source of truth with owner/admin confirmation or import them into a quarantine/review table later.

## Weight Duplicate Classification

The issue report found 34 same-pig/same-date weight duplicate groups.

### Likely Duplicate Same Weight

These groups have the same pig, same date, and same weight value. They are likely duplicate artifacts and should be deduplicated during import by keeping one canonical event and retaining duplicate source references in audit metadata.

Likely duplicate groups: 25.

Examples:

- `PIG-2026-04A0`, `2026-05-11`, weight `5.2`, 2 rows
- `PIG-2026-0874`, `2026-02-23`, weight `15.2`, 2 rows
- `PIG-2026-8FFC`, `2026-02-02`, weight `27.2`, 3 rows
- `PIG-2026-92F3`, `2026-05-04`, weight `126.4`, 2 rows
- `PIG-2026-E716`, `2026-05-11`, weight `44`, 2 rows

### Conflicting Weight Groups

These groups have the same pig and same date but different weight values. They must not be auto-deduplicated without a rule.

Conflicting groups: 9.

| Pig | Date | Values | Recommendation |
| --- | --- | --- | --- |
| `PIG-2026-0874` | `2026-02-02` | `16.4`, `12.2` | owner/admin review |
| `PIG-2026-12D8` | `2026-03-23` | `2.3`, `2.8` | owner/admin review |
| `PIG-2026-3E84` | `2026-03-02` | `110.8`, `10.8` | likely typo/correction; review |
| `PIG-2026-42B7` | `2026-05-04` | `130`, `132.4` | review |
| `PIG-2026-6D24` | `2026-05-11` | `3.39`, `3.4` | likely rounding/correction; review |
| `PIG-2026-8FFC` | `2026-02-09` | `27.2`, `32.8` | review |
| `PIG-2026-A5EA` | `2026-03-17` | `37.4`, `36.6` | review |
| `PIG-2026-E926` | `2026-05-11` | `10.8`, `9.2` | review |
| `PIG-2026-EFB3` | `2026-05-25` | `54.4`, `55.2` | review |

Recommendation: GS-MIG-3 should import conflicting groups only after a policy is approved. Conservative default: keep the latest source row as canonical only when source ordering/timestamp proves correction intent; otherwise hold the group for owner/admin review.

## Location Duplicate Classification

The issue report found one repeated movement group:

| Pig | Date | From pen | To pen | Rows | Recommendation |
| --- | --- | --- | --- | ---: | --- |
| `PIG-2026-9613` | `2026-06-22` | `PEN-013` | `PEN-012` | 7 | likely duplicate same movement |

All seven rows have reason `Moved during durable duplicate weight review`.

Recommendation: deduplicate to one canonical movement event during import, but keep all source row references in audit metadata. Do not write this policy until approved.

## Proposed Import Policies For Owner Review

Recommended default policies:

1. Missing `Pig_ID` weight rows: exclude from canonical import and record in an import review/quarantine report unless owner/admin supplies the pig id.
2. Same-pig/same-date/same-weight duplicates: import one canonical weight event; preserve all original source row references in `source_sheet_row`/audit metadata.
3. Same-pig/same-date conflicting weights: block from automatic import unless a correction rule is approved.
4. Same-pig/same-date/same-to-pen duplicate movements: import one canonical movement event; preserve source references.
5. Formula sheets remain compare-only until formula-equivalence tests pass.

## GO / NO-GO

GO for owner review of the data issue policy.

NO-GO for applying the migration or importing production data until the owner approves:

- missing `Pig_ID` handling
- duplicate weight handling
- conflicting weight handling
- duplicate movement handling
- whether a review/quarantine table is needed before import

## Tests Run

Passed:

- `.\venv\Scripts\python.exe -m unittest tests.test_google_sheets_farm_import_dry_run`
- `.\venv\Scripts\python.exe -m py_compile scripts\google_sheets_farm_import_dry_run.py`

Live read-only diagnostic:

- `.\venv\Scripts\python.exe scripts\google_sheets_farm_import_dry_run.py --issue-report`

Safety confirmation:

- no migration applied
- no Supabase writes
- no Google Sheets writes
- no customer sends
- no public posts
- no payments/deposits
- no reservations
- no lifecycle/purpose writes
