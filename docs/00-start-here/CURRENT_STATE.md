# Current State

This is the short live-state dashboard for the project. Keep it current after accepted phases, PR merges, and deploys.

## Production State

`origin/main` currently includes:

- `560a345` Add owner logout controls (#4)
- `97e63a0` Add owner access session guard for SAM reads (#3)
- `7d7dc7e` Add read-only SAM command state endpoint (#2)
- `e41d4a6` Polish SAM meat sales full-width dashboard
- `f6487da` Improve SAM meat sales command room (#1)
- `ed3a27d` Improve bulk weight duplicate and movement handling

Render deploys from `main` unless the service configuration says otherwise.

## Active Branches / PRs

- Cleanup work must use clean worktrees from `origin/main`.
- Do not merge polluted branches such as old SAM release branches or CHARLIE planning branches unless a later owner-approved cleanup explicitly says so.

## Current Access Status

- `OWNER_ACCESS_ENABLED` is supported.
- Owner login/session exists.
- Owner logout UX exists.
- Tokens must not be committed.
- Render env vars must be configured separately.
- `/sales/meat-leads` is owner protected when owner access is enabled.

Required owner access env vars:

- `OWNER_ACCESS_ENABLED`
- `OWNER_ACCESS_ALLOW_LOCAL_DEV`
- `OWNER_READ_TOKEN`
- `OWNER_ADMIN_TOKEN`
- `OWNER_SESSION_SECRET`

## SAM Status

- SAM Meat Sales Command Room is live.
- Full-width layout is live.
- Read-only command-state endpoint is live.
- Frontend has not yet been switched to command-state.
- Next SAM phase after cleanup: Phase 3A.6 frontend consumes command-state with fallback.

SAM safety remains unchanged:

- no one-click send chain
- no automatic payment/deposit action
- no automatic reservation
- no public posting
- no price, stock, slaughter, butcher, or delivery promise without approved rails

## Oom Sakkie Status

- Oom Sakkie remains Farm Commander under CHARLIE.
- Warm farm command-center direction remains.
- Oom Sakkie UI must not inherit CHARLIE dark styling.
- Oom Sakkie remains behind its own safety and owner approval rails.

## CHARLIE Status

- CHARLIE is the planned top-level owner operating layer.
- CHARLIE is not built yet as a production UI.
- First CHARLIE surface must be owner-only and read-only/draft-only.

## FRED Status

- FRED is the planned future Transport Commander.
- FRED is not built yet.
- No dispatch, quote, payment, or customer-send automation is approved.

## Ledger Status

- Agent Collaboration Ledger design exists as a planning direction.
- SQL is not implemented in production by this cleanup.
- No ledger migration is approved yet.

## Known Risks

- Original `sam-meat-command-room-release` worktree is dirty and polluted.
- Old docs and phase notes contain noise and stale architecture wording.
- Old screenshots and `external_sources` need later owner review before archive/delete.
- Mutation route guards still need ACCESS-2 later.
- Frontend command-state consumption has not been implemented yet.
- `planning/ToDoList.md` contains fresh owner issue notes that need triage, not deletion.

## Last Updated

2026-06-28
