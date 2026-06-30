# Workflow

This file defines how owner notes become scoped work without creating a second roadmap.

## Intake

The owner can dump rough ideas, bugs, screenshots, and prompts into `planning/ToDoList.md` for now.

Later, use the inbox structure described in `OWNER_INBOX_GUIDE.md`.

`planning/ToDoList.md` is scratch. It is not production truth and it is not the roadmap.

If a note is important, copy or summarize it into `NEXT_STEPS.md` and keep enough context in `CURRENT_STATE.md` for the next session to understand the live risk.

Owner mission intake can also come from `planning/CODEX_CHAT.md` or Telegram through CHARLIE Build Relay. Both paths must follow `CHARLIE_MISSION_PROTOCOL.md` and normalize into the same mission contract before build work starts.

Supabase `charlie_missions` is the durable mission queue. `planning/CODEX_CHAT.md` remains the laptop-friendly active mission scratchpad.

## Triage

Cursor/Codex triages owner notes into:

- `docs/00-start-here/NEXT_STEPS.md` for priority and phase planning
- `docs/00-start-here/CURRENT_STATE.md` for live-state updates
- a module doc only when the note is a durable module decision
- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md` only when mission governance rules change

After each accepted phase or deploy, update `CURRENT_STATE.md` before moving on.

## Priority Model

- P0: live or operational issue
- P1: money path or sales
- P2: active build
- P3: planned build
- P4: backlog or idea

## Phase Rules

Every phase should define:

- scope
- allowed files
- forbidden files
- tests or checks
- report format
- owner approval point before merge/deploy when risky

Auth, security, backend, migrations, sends, payments, reservations, public posts, and production data changes need extra care and usually require a PR.

## Release Discipline

Use one clean terminal/worktree for releases.

Do not do release work from a dirty or polluted branch.

Do not use multi-terminal coding unless a later workflow explicitly controls separate worktrees.

For cleanup and releases, prefer one clean worktree created from `origin/main`.

Never use `git add .`.

Never commit `.env`, tokens, screenshots, `test-results`, `external_sources`, `.claude`, or unrelated owner files unless a later owner approval explicitly says so.

## Safety Rails

Gatekeeper and owner approvals remain hard boundaries.

No customer send, public post, payment/deposit action, reservation, dispatch, stock allocation, farm record write, hardware control, migration, or deployment may bypass its approved rail.
