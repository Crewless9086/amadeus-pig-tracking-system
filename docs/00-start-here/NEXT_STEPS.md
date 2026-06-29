# Next Steps

This is the active priority queue. Raw notes belong in `planning/ToDoList.md` or `planning/inbox/`, then get triaged here.

## P0 Operational / Live Issues

- P0 Bulk Weight Data-Loss Fix: owner entered 71 rows, 60 were recorded in the draft/session, upload failed with a vague error, refresh lost all typed rows. Branch: `p0-bulk-weight-draft-recovery`.
- P0 Bulk Upload HTML/JSON Failure: owner entered 73 entries with about 21 pen changes; upload returned HTML/non-JSON (`Unexpected token '<'`) instead of structured JSON. JSON-safe hotfix is merged, but live retest still failed through the old synchronous path.
- P0 Supabase-First Durable Bulk Rail: merged, but owner-facing staging/chunk mechanics are confusing and must be hidden.
- P0 One-Button Bulk Owner Flow: active branch `p0-bulk-one-button-owner-flow`; existing staged batch `2241aeab-4f40-4797-882d-1588a17abbd0` is `processing` with 10 rows stuck in `processing`, 32 still `staged`, 31 already recorded, and 43 blank/no-change skipped.
- Owner-facing rule: the visible workflow is Save Draft, Upload Weights, Download Draft, Import Draft. `Upload Weights` must stage/resume/process/retry automatically; Continue Upload, batch id, JSON/non-JSON status, and chunk mechanics must not be primary owner actions/messages.
- Bulk-weight draft recovery requirement: typed rows must autosave to durable browser storage, survive refresh, survive upload failure, import from downloaded draft JSON, preserve `batch_id`, and remain exportable until a complete confirmed upload clears them.
- Do not ask the owner to manually re-enter/test 71 or 73 rows again until automated existing-batch resume, one-button Upload Weights, interrupted `processing` row recovery, import/download, failure/retry, duplicate/already-recorded, and blank/no-change wording tests pass and the fix is deployed.
- Decision made: Google Sheets/Render synchronous upload is not reliable enough for large weekly batches; use Supabase batch/audit rail before downstream Sheets sync, but hide that complexity from the owner.
- GS-MIG-0 Google Sheets to Supabase migration deep dive is active as report-only planning on `gs-to-supabase-deep-dive-plan`. Do not implement schema/code/cutover until owner approves a specific migration phase.
- GS-MIG-1 is merged as PR #19: additive canonical farm schema proposal plus dry-run Google Sheets import/reconciliation tooling.
- GS-MIG-2 is merged as PR #20. No migration has been applied and no production data has been written.
- GS-MIG-3A is merged as PR #21.
- GS-MIG-3B is merged as PR #22.
- GS-MIG-3 is merged as PR #23.
- GS-MIG-4 additive schema apply is complete: canonical farm tables/views exist in Supabase.
- GS-MIG-5 initial import plan is merged as PR #24.
- GS-MIG-5 controlled import execution is complete: Supabase now contains the clean canonical farm import batch `GS-MIG-5-2026-06-29`.
- Owner decision: missing-`Pig_ID` weight rows are left out of canonical import and listed in review/quarantine output; same-weight duplicates import as one canonical event; conflicting weights stay on a visible review list and do not import automatically; repeated movements import as one canonical movement.
- Import result: 217 pigs, 20 pens, 1,190 weight events, 179 location events, 261 medical events, 17 litters, 15 mating events, 3 products, and 18 settings were imported. The 9 conflicting-weight groups remain excluded for review.
- GS-MIG-6 is merged as PR #26.
- GS-MIG-7 is active on `gs-mig-7-supabase-route-cutover`: route-by-route Supabase read cutover for safe direct canonical farm routes.
- GS-MIG-7A direct canonical reads: pigs, pens, products, parent options, pig detail, family tree, weight history, movement history, treatment history, latest weight, weights-by-date, and weight report.
- Do not patch bulk weights again until the migration scope is understood, except for an explicitly approved P0 owner-flow hotfix.
- OP-1.2 Evidence Push: read-only data inspection and non-mutating pressure probes have raised several tickets to the 96% build gate.
- OP-009 SAM Pilot Readiness 500 Fix: build-ready at 96%; targeted non-mutating probe proved per-lead source exceptions can bubble into a 500.
- OP-002 Bulk Weight Reliability And Audit Trail: build-ready at 96%; mocked 71-row pressure probe proved partial-success behavior and the audit/UI fix direction.
- OP-010 Owner Logout Redirect Preference: build-ready at 98%; change logout redirect to the main dashboard `/` only after OP-1.2 is accepted.
- Keep Render owner access env vars correct, especially `OWNER_ACCESS_ENABLED`, token values, and session secret.
- Do not commit `.env`, tokens, screenshots, test-results, external sources, or unrelated owner files.

## P1 Money Path

- OP-001 Meat Lead Creation And Qualification: build-ready at 96%; read-only Supabase inspection proved weak owner-labeled chats are current lead rows with unknown product and missing facts.
- OP-003 Meat Planning Weight Window Settings: planning-ready at 96%; owner defaults are 60-80kg meat and 80kg+ abattoir/cull, including heavy culls.
- OP-007 Sales Dashboard Meat-Ready Stock Visibility: build-ready at 96%; read-only dashboard and allocation sources were confirmed.
- OP-008 Current Stock Value And Sale Readiness Model: build-ready at 96%; price, stock, weight/status sources and owner freshness rule are confirmed.
- Keep no-send, no-payment, no-reservation, and no-public-post gates intact.

## P2 Current Build

- GS-MIG-0: create Google Sheets to Supabase migration plan. Report-only; no code, migrations, production writes, Google Sheets edits, or behavior changes.
- GS-MIG-1: merged as PR #19. No app cutover, no migration application, and no production writes.
- GS-MIG-2: merged as PR #20.
- GS-MIG-3A: merged as PR #21.
- GS-MIG-3B: merged as PR #22.
- GS-MIG-3: merged as PR #23.
- GS-MIG-4: additive schema applied.
- GS-MIG-5: controlled initial import executed. Do not cut over app routes until the review/backfill verification phase is complete and explicitly approved.
- GS-MIG-6: merged as PR #26.
- GS-MIG-7: route-by-route Supabase read cutover. Direct canonical read routes first; formula-heavy routes only after equivalence tests/reports.
- OP-1 Operational Master Plan: created tickets OP-001 through OP-010 from 2026-06-28 owner notes.
- OP-1.2 is active: read-only Supabase/Sheets inspection, existing tests, and non-mutating probes are recorded in the evidence log.
- OP-BUILD-1A is ready for owner approval: OP-010 logout redirect and OP-009 pilot readiness degraded handling.
- Cleanup is paused except for owner-approved inventory/index work.
- ACCESS-2 planning/implementation later for mutation routes.
- Keep `planning/ToDoList.md` preserved; do not wipe owner notes without explicit approval.

## P3 Planned Build

- OP-004 Pig Allocation Purpose Review Workflow.
- OP-005 Beacon Full-Width Command UI Plan.
- OP-006 Pig Detail Full-Width Web View Plan.
- Phase 3A.6: SAM frontend consumes the read-only command-state endpoint with fallback only after OP-009 is fixed or safely degraded.
- Agent Collaboration Ledger SQL review and migration later.
- CHARLIE read-only owner cockpit.
- FRED transport MVP planning/build.
- Oom Sakkie visual/asset cleanup later.

## P4 Ideas / Backlog

- Obsidian optional only.
- External Jarvis/ZOEY/OpenCove tools are not the core.
- Agent portraits and voices later.
- Planning inbox folder structure:
  - `planning/inbox/notes/`
  - `planning/inbox/screenshots/`
  - `planning/inbox/prompts/`
  - `planning/inbox/raw-cursor-reports/`
  - `planning/inbox/processed/`

## Blocked / Waiting

- Tickets below 96% confidence are not build-ready: OP-004, OP-005, and OP-006.
- Google Sheets vs Supabase decision for bulk weights is resolved for the current P0: build Supabase-first durable staging/audit with Google Sheets as downstream sync.
- Full Google Sheets to Supabase app cutover remains incomplete. GS-MIG-7 may cut over safe direct canonical read routes with fallback.
- Formula-heavy route cutover remains blocked until equivalence tests/reports exist for dashboard, sales dashboard, pig allocation readiness, sales availability, meat planning, and litter overview/detail.
- Do not implement Phase 3A.6 until OP-009 is fixed and verified as degraded-safe.
- Do not archive, delete, or move screenshots/external sources until owner review.
- Do not implement CHARLIE/FRED/Ledger SQL until their phases are explicitly approved.
- Static agent assets need asset-register review before any commit or cleanup.

## Done Since Last Review

- Archive local markdown planning docs: `fe1c71f`.
- Owner-note triage into active docs: `afefb5f`.
- Docs inbox/archive governance: `ed2f1c3`.
- CLEANUP-1 start-here docs workflow: `2de81f2`.
- Pig Tracker bulk-weight deploy: `ed3a27d`.
- SAM Command Room: `f6487da`.
- SAM full-width layout: `e41d4a6`.
- SAM read-only command-state endpoint: `7d7dc7e`.
- Owner access session guard: `97e63a0`.
- Owner logout UX: `560a345`.

