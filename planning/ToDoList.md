# Scratch (`planning/ToDoList.md`)

Use this as the live scratchpad for owner notes, live-test findings, rough ideas, bugs, and next mission input.

Codex/Cursor must triage these notes into the active docs before implementation:

- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`
- relevant `docs/06-operations/` plans or evidence logs
- `planning/inbox/processed/YYYY-MM/` when raw notes need preservation

Do not silently delete owner notes until they are processed into the correct place.

---

## Live Test Notes

Write new live-test findings here.

```text

```
---

## New Mission Notes

Write the next concept/problem/improvement here if it is not already in `planning/CODEX_CHAT.md`.

```text

```

---

## Processed / Logged

- 2026-06-30: Litter status/live-test note processed. `/litters` now derives useful sheet-fallback litter statuses instead of showing blank/Unknown where possible, and `/litter/<id>` lifecycle outcome counts classify `Died` as dead instead of other/active. Evidence: `tests.test_pig_weights_litter_service`, `tests.test_farm_supabase_read_service`, `tests.test_pig_weights_dashboard_service`, `tests.test_frontend_route_contracts`, `node --check static/js/litters.js`, and `node --check static/js/litterDetail.js`.
- 2026-06-30: Live app review notes converted into CHARLIE mission queue records and preserved in `planning/inbox/processed/2026-06/ToDoList_2026-06-30_live_app_review_notes.md`.
- 2026-06-30: CHARLIE Codex pickup bridge moved into active build. Goal: a running Codex/Cursor session can pull the next approved Telegram mission into `planning/CODEX_CHAT.md` and mark it `in_progress`.
- 2026-06-30: CHARLIE command-console mission protocol moved into active build. Telegram and `planning/CODEX_CHAT.md` will share `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`; approve/pause/reject commands record decisions only.
- 2026-06-30: CHARLIE mission queue and owner notification helper moved into active build on `charlie-relay-mission-queue`. Supabase mission queue migration was applied; Telegram remains non-executing.
- 2026-06-30: CHARLIE Build Relay v0 mission accepted from `planning/CODEX_CHAT.md`. Scope is owner-only Telegram command/notification relay with strict safety gates; no dangerous Telegram authority.
- 2026-06-29: Google Sheets to Supabase migration closeout was logged in `docs/06-operations/GS_MIG_FINAL_AUDIT.md`.
- 2026-06-29: PR #39 merged as `66f7f71 Complete Google Sheets migration final audit (#39)`.
- Current status: no remaining Google Sheets caller is classified as an active app route that still must be migrated. Remaining callers are safe fallback only, import/export/admin tooling, legacy/reference wrappers, or tests.
