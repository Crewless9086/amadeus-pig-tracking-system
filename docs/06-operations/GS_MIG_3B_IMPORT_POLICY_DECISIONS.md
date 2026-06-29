# GS-MIG-3B Import Policy Decisions

Date: 2026-06-29

Branch: `gs-mig-3b-import-policy`

Mode: owner decision capture. No migration was applied. No Supabase writes, Google Sheets writes, production data rewrites, customer sends, public posts, payments, reservations, or lifecycle/purpose writes were performed.

## Owner Decisions

The owner approved these import policies after reviewing GS-MIG-3A:

1. Missing `Pig_ID` weight rows:
   - If a `WEIGHT_LOG` row has no `Pig_ID`, leave it out of the canonical weight import.
   - Do not guess the pig.
   - Preserve the skipped row in an import review/quarantine report.

2. Same-pig/same-date/same-weight duplicates:
   - Import only one canonical weight event.
   - Do not import duplicate copies.
   - Preserve all source row references in audit/review metadata.

3. Conflicting same-pig/same-date weights:
   - Do not auto-import.
   - Put each conflict on a review list.
   - The review list must show the pig, date, candidate weight values, source sheet rows, and source weight log IDs.
   - The owner/admin must later choose the correct weight, mark the group as excluded, or approve a correction rule.

4. Repeated same-pig/same-date/same-to-pen movements:
   - Import only one canonical movement event.
   - Do not import duplicate copies.
   - Preserve all source row references in audit/review metadata.

## How Conflicting Weights Will Be Reviewed

Conflicting weights will not disappear.

The import tooling should create a review output before any production import:

- `review_type`: `conflicting_weight`
- `pig_id`
- `weight_date`
- candidate weight values
- source sheet rows
- source `Weight_Log_ID` values
- recommended action: `owner_review_required`
- selected canonical value: blank until owner/admin decides
- decision status: `pending`, `approved`, `excluded`, or `resolved_by_rule`

Until a conflict is resolved:

- it must not become a canonical `pig_weight_events` row
- it must not affect current-weight calculations
- it must not affect meat readiness, allocation, or stock valuation
- it must remain visible in the migration review report

## Current Known Review Items

From GS-MIG-3A:

- 6 missing-`Pig_ID` `WEIGHT_LOG` rows: skip from canonical import and list in review/quarantine output.
- 25 likely same-weight duplicate groups: import one canonical event per group and preserve duplicate source references.
- 9 conflicting same-pig/same-date weight groups: hold for review.
- 1 likely duplicate movement group: import one canonical event and preserve source references.

## GS-MIG-3 Implementation Requirements

Before any production import:

- add import review/quarantine output for skipped and conflicting records
- prove same-weight duplicates collapse to one canonical event
- prove repeated movements collapse to one canonical event
- prove conflicting weights are excluded from canonical import until reviewed
- prove no skipped/conflicting row is silently lost
- keep all original source identifiers for traceability

## GO / NO-GO

GO to use these policies when designing GS-MIG-3.

NO-GO for applying the migration or importing data until GS-MIG-3 implementation is explicitly approved.
