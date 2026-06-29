# GS-MIG-7 Supabase Route Cutover Report

Date: 2026-06-29

## Status

In progress on branch `gs-mig-7-supabase-route-cutover`.

This phase moves safe read-only farm routes from Google Sheets to Supabase canonical tables/views, one batch at a time. Routes fall back to the existing Google Sheets path when `DATABASE_URL` is not configured or a Supabase read fails.

## Safety

- No migrations added.
- No Google Sheets writes.
- No Supabase writes.
- No customer sends, public posts, payments, reservations, or lifecycle/purpose writes.
- No Phase 3A.6, CHARLIE, FRED, or ledger work.

## Batch 7A: Direct Canonical Read Routes

These routes now prefer Supabase canonical reads:

- `/api/pig-weights/pigs`
- `/api/pig-weights/pens`
- `/api/pig-weights/products`
- `/api/pig-weights/parent-options`
- `/api/pig-weights/pig/<pig_id>`
- `/api/pig-weights/pig/<pig_id>/family-tree`
- `/api/pig-weights/pig/<pig_id>/weights`
- `/api/pig-weights/pig/<pig_id>/movements`
- `/api/pig-weights/pig/<pig_id>/treatments`
- `/api/pig-weights/pig/<pig_id>/latest-weight`
- `/api/pig-weights/weights-by-date`
- `/api/pig-weights/weight-report`

## Not Cut Over Yet

These routes remain on Google Sheets/formula logic until formula-equivalence or domain-specific Supabase services are added:

- `/api/pig-weights/dashboard`
- `/api/pig-weights/sales-dashboard`
- `/api/pig-weights/sales-availability`
- `/api/pig-weights/litters`
- `/api/pig-weights/litter/<litter_id>`
- Mutation/write routes.

## Batch 7C: Allocation And Meat Planning Reads

`/api/pig-weights/pig-allocation-readiness` now prefers Supabase canonical inputs while reusing the existing allocation business rules.

`/api/pig-weights/meat-planning` builds from allocation readiness, so it now follows the Supabase allocation path when `DATABASE_URL` is available.

Live read-only smoke:

- Allocation source: `supabase_canonical`
- Allocation total: 217 pigs
- Allocation buckets: Needs Data 39, Needs Classification 22, Growing 13, Livestock Candidate 19, Slaughter Candidate 0, Meat Candidate 2, Retain / Breeding Candidate 21, Allocated 0, Exited 101
- Meat-planning rows: 2
- Meat-planning summary: ready now 2, next 14 days 0, next 30 days 0, future 0, fallback abattoir 0

Still not cut over:

- dashboard litter attention
- sales dashboard
- sales availability and stock formulas
- litter overview/detail formulas
- mutation/write routes

## Local Environment Note

The local shell does not currently expose `DATABASE_URL`, so live Supabase smoke reads could not run from this environment. Unit tests use fakes/mocks to verify Supabase read shapes and fallback behavior.

## Tests Run

- `python -m unittest tests.test_farm_supabase_read_service`
- `python -m unittest tests.test_pig_weights_report_service`
- `python -m unittest tests.test_pig_weights_dropdown_options`
- `python -m unittest tests.test_frontend_route_contracts`
- `python -m unittest tests.test_pig_allocation_readiness_service tests.test_pig_weights_bulk_service tests.test_pig_weights_litter_service`

## Next

Build formula-equivalence services/reports before cutting over dashboard, allocation, litter overview, sales dashboard, sales availability, and meat planning routes.
