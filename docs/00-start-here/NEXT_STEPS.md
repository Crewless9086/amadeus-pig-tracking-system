# Next Steps

This is the active priority queue. Raw notes belong in `planning/ToDoList.md` or the future inbox, then get triaged here.

## P0 Operational / Live Issues

- Verify owner logout works live after ACCESS-1.1 deploy.
- Keep Render owner access env vars correct.
- Do not commit `.env`, tokens, screenshots, test-results, external sources, or unrelated owner files.
- Investigate reported SAM pilot readiness `500` on `/sales/meat-leads`.
- Investigate owner report that one-word Chatwoot messages became meat leads too easily.
- Investigate bulk weight partial upload/reporting concern from the owner note before doing more Pig Tracker changes.

## P1 Money Path

- SAM Phase 3A.6: frontend consumes the read-only command-state endpoint with fallback to existing frontend computation.
- Keep no-send, no-payment, no-reservation, and no-public-post gates intact.
- Clarify meat planning settings for meat window and abattoir window before adding write controls.
- Review whether Sales Overview should show meat-ready stock and current stock value planning.

## P2 Current Build

- CLEANUP-1: active start-here docs and owner intake workflow.
- ACCESS-2 planning/implementation later for mutation routes.
- Triage `planning/ToDoList.md` into this file after owner approves touching it.

## P3 Planned Build

- Agent Collaboration Ledger SQL review and migration later.
- CHARLIE read-only owner cockpit.
- FRED transport MVP planning/build.
- Oom Sakkie visual/asset cleanup later.
- Beacon media page full-width/readability redesign.
- Pig detail page full-width dashboard layout.
- Pig allocation review/action planning.

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

- Do not archive, delete, or move screenshots/external sources until owner review.
- Do not edit old untracked start-here handover docs until owner approves a cleanup phase for them.
- Do not implement CHARLIE/FRED/Ledger SQL until their phases are explicitly approved.

## Done Since Last Review

- Pig Tracker bulk-weight deploy: `ed3a27d`.
- SAM Command Room: `f6487da`.
- SAM full-width layout: `e41d4a6`.
- SAM read-only command-state endpoint: `7d7dc7e`.
- Owner access session guard: `97e63a0`.
- Owner logout UX: `560a345`.
