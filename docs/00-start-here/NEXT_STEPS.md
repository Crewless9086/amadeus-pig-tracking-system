# Next Steps

This is the active priority queue. Raw notes belong in `planning/ToDoList.md` or the future inbox, then get triaged here.

## P0 Operational / Live Issues

- Verify owner logout works live after ACCESS-1.1 deploy from `560a345`.
- Review logout redirect preference: owner asked whether logout from SAM can land on the dashboard instead of the sign-in page.
- Keep Render owner access env vars correct, especially `OWNER_ACCESS_ENABLED`, token values, and session secret.
- Do not commit `.env`, tokens, screenshots, test-results, external sources, or unrelated owner files.
- Investigate reported SAM pilot readiness `500` on `/sales/meat-leads`.
- Investigate owner report that one-word Chatwoot messages became meat leads too easily.
- Investigate bulk weight partial upload/reporting concern from the owner note before doing more Pig Tracker changes.
- Confirm whether bulk weight reliability needs a Google Sheets timeout fix, Supabase-backed write path, or better audit/log trail before weekly use continues.

## P1 Money Path

- SAM Phase 3A.6: frontend consumes the read-only command-state endpoint with fallback to existing frontend computation.
- Keep no-send, no-payment, no-reservation, and no-public-post gates intact.
- meat lead creation quality: explain current lead creation rules, then plan stricter lead qualification so short/noisy chats do not become real sales leads too easily.
- meat planning weight windows: clarify current meat window and abattoir window settings on `/meat-planning`; owner suggested meat window 60-80kg and abattoir window 80kg+.
- sales stock questions: confirm whether `/sales-dashboard` Available Stock shows meat-ready stock; add planning if the current table does not answer that clearly.
- Current stock value planning: design a future value view for livestock, meat, slaughter-to-butcher, slow growers, and sales availability decisions.

## P2 Current Build

- CLEANUP-4B: triage fresh owner notes from `planning/ToDoList.md` into active docs.
- Keep cleanup conservative: no archive, move, delete, restore, or asset cleanup until separately approved.
- ACCESS-2 planning/implementation later for mutation routes.
- Keep `planning/ToDoList.md` preserved; do not wipe owner notes without explicit approval.

## P3 Planned Build

- Agent Collaboration Ledger SQL review and migration later.
- CHARLIE read-only owner cockpit.
- FRED transport MVP planning/build.
- Oom Sakkie visual/asset cleanup later.
- Beacon media page full-width/readability redesign.
- Pig detail page full-width dashboard layout.
- Pig allocation review/action planning.
- pig allocation workflow: define how owner reviews recommendations on `/pig-allocation`, drills into an animal, and assigns purpose safely.

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
- Static agent assets need asset-register review before any commit or cleanup.

## Done Since Last Review

- Docs inbox/archive governance: `ed2f1c3`.
- CLEANUP-1 start-here docs workflow: `2de81f2`.
- Pig Tracker bulk-weight deploy: `ed3a27d`.
- SAM Command Room: `f6487da`.
- SAM full-width layout: `e41d4a6`.
- SAM read-only command-state endpoint: `7d7dc7e`.
- Owner access session guard: `97e63a0`.
- Owner logout UX: `560a345`.
