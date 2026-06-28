# Next Steps

This is the active priority queue. Raw notes belong in `planning/ToDoList.md` or `planning/inbox/`, then get triaged here.

## P0 Operational / Live Issues

- P0 Bulk Weight Data-Loss Fix: owner entered 71 rows, 60 were recorded in the draft/session, upload failed with a vague error, refresh lost all typed rows. Branch: `p0-bulk-weight-draft-recovery`.
- P0 Bulk Upload HTML/JSON Failure: owner entered 73 entries with about 21 pen changes; upload returned HTML/non-JSON (`Unexpected token '<'`) instead of structured JSON. Branch: `p0-bulk-upload-json-durable`.
- Bulk-weight draft recovery requirement: typed rows must autosave to durable browser storage, survive refresh, survive upload failure, and remain exportable until a complete confirmed upload clears them.
- Do not ask the owner to manually re-enter/test 71 or 73 rows again until automated 73-row + pen-change pressure tests and non-JSON response tests pass and the fix is deployed.
- Decision point: if Google Sheets/Render synchronous upload still returns platform HTML or times out outside app control, move to a Supabase-first durable batch rail.
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
- Google Sheets vs Supabase decision for bulk weights remains open.
- Migration decisions are blocked until a specific OP build proves one is required.
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

