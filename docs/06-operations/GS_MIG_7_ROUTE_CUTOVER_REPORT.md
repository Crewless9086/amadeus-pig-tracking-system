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
- litter overview/detail formulas
- mutation/write routes

## Batch 7D: Sales Availability And Stock Reads

`/api/pig-weights/sales-availability` now derives from Supabase-backed allocation readiness when available.

`/api/pig-weights/sales-dashboard` now returns:

- Supabase-derived `totals`
- Supabase-derived `summary`
- `meat_ready_stock` from the existing meat-ready stock model

Live read-only smoke:

- Sales stock summary rows: 7
- Sales stock total rows: 4
- Sales availability rows: 217
- Available-for-sale rows under the new allocation-derived model: 39
- Sales dashboard response keys: `success`, `totals`, `summary`, `meat_ready_stock`
- Meat-ready stock groups: 6

Still not cut over:

- dashboard litter attention
- litter overview/detail formulas
- mutation/write routes

## Batch 7E: Litter Overview, Detail, And Dashboard Attention Reads

These routes/services now prefer Supabase canonical reads:

- `/api/pig-weights/litters`
- `/api/pig-weights/litter/<litter_id>`
- dashboard litter attention summary

The Supabase path covers canonical litter count review and keeps the existing Google Sheets fallback when `DATABASE_URL` is unavailable or Supabase read fails. The legacy Sheets fallback remains the source for older formula-specific/newborn-health attention rules until those are replaced with explicit Supabase services.

Live read-only smoke:

- Litter overview source: `supabase_canonical`
- Litter overview count: 17
- Litter attention count: 1
- Litter mismatch count: 1
- First detail smoke: `LIT-2026-1025`, 9 linked pig records
- Dashboard litter attention source: `supabase_canonical`
- Dashboard litter attention count: 1

Still not cut over:

- mutation/write routes
- formula-specific newborn-health attention replacement rules

## Batch 7F: Breeding And Mating Read Routes

These read routes now prefer Supabase canonical reads:

- `/api/pig-weights/breeding-options`
- `/api/pig-weights/matings`
- `/api/pig-weights/breeding-analytics`
- `/api/pig-weights/breeding-analytics/<pig_id>`

POST/write routes for creating matings, assuming pregnancy, marking not pregnant, and linked movement updates remain on the existing guarded path and were not cut over.

Live read-only smoke:

- Breeding options source: `supabase_canonical`
- Sows: 18
- Boars: 3
- Mating overview count: 15
- Breeding analytics source: `supabase_canonical`
- Breeding analytics summary: 19 sow records, 3 boar records, 15 mating records, 17 litter records
- Breeding animal detail smoke returned HTTP 200 with read-only detail.

Still not cut over:

- mutation/write routes
- formula-specific newborn-health attention replacement rules
- order/sales workflow read/write modules outside farm canonical data

## Inspected But Not Cut Over

These areas were inspected during GS-MIG-7 and intentionally left on the existing path:

- Dashboard summary reserved/withdrawal counts: `pig_current_state` does not yet expose reservation or withdrawal-clear fields, so a full dashboard summary cutover would either lose counts or need a schema/view extension.
- Order read routes: Supabase order tables exist, but the current imported order boundary appears to be shadow/partial data rather than the complete live order source. Cutting over `list_orders()` or `get_order_detail()` now could hide live Google Sheets orders.
- Mutation/write routes: creating/updating pigs, matings, litters, treatments, reservations, lifecycle status, order lines, and sales actions still require separate durable write rails and owner-approved cutover phases.

## Local Environment Note

Live read-only Supabase smoke reads ran from the local environment after loading `.env`. Unit tests use fakes/mocks to verify Supabase read shapes and fallback behavior.

## Tests Run

- `python -m unittest tests.test_farm_supabase_read_service`
- `python -m unittest tests.test_pig_weights_report_service`
- `python -m unittest tests.test_pig_weights_dropdown_options`
- `python -m unittest tests.test_frontend_route_contracts`
- `python -m unittest tests.test_pig_allocation_readiness_service tests.test_pig_weights_bulk_service tests.test_pig_weights_litter_service`
- `python -m unittest tests.test_farm_supabase_read_service tests.test_pig_weights_litter_service tests.test_frontend_route_contracts tests.test_pig_weights_dashboard_service`
- `python -m unittest tests.test_farm_supabase_read_service tests.test_breeding_analytics_service tests.test_mating_service tests.test_mating_routes`

## Next

Continue replacing remaining Google Sheets formula-specific logic with explicit Supabase services, then cut over mutation/write routes only after separate owner-approved durable write rails and tests.
