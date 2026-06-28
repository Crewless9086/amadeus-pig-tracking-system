# Workflow

This file defines how owner notes become scoped work without creating a second roadmap.

## Intake

The owner can dump rough ideas, bugs, screenshots, and prompts into `planning/ToDoList.md` for now.

Later, use the inbox structure described in `OWNER_INBOX_GUIDE.md`.

`planning/ToDoList.md` is scratch. It is not production truth and it is not the roadmap.

## Triage

Cursor/Codex triages owner notes into:

- `docs/00-start-here/NEXT_STEPS.md` for priority and phase planning
- `docs/00-start-here/CURRENT_STATE.md` for live-state updates
- a module doc only when the note is a durable module decision

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

Never use `git add .`.

Never commit `.env`, tokens, screenshots, `test-results`, `external_sources`, `.claude`, or unrelated owner files unless a later owner approval explicitly says so.

## Safety Rails

Gatekeeper and owner approvals remain hard boundaries.

No customer send, public post, payment/deposit action, reservation, dispatch, stock allocation, farm record write, hardware control, migration, or deployment may bypass its approved rail.
