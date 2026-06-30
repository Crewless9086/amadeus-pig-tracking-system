# CHARLIE Build Relay Plan

## 1. Executive Decision

CHARLIE Build Relay is the first practical step toward CHARLIE as the owner command layer.

Telegram should not control the repository directly. Telegram is the owner command and notification surface. The repository docs remain the active mission truth. Codex/Cursor remains the builder. The relay must preserve hard stops around production data, migrations, sends, posts, payments, reservations, lifecycle changes, merges, and deploys.

## 2. Current Implementation

This phase adds a safe v0 relay:

- `POST /api/charlie/build-relay/telegram/webhook`
- `GET /api/charlie/build-relay/policy`
- owner allowlist by Telegram user id
- Telegram webhook secret verification
- disabled by default
- direct Telegram replies through the configured CHARLIE bot token when enabled
- `/status`, `/next`, `/mission`, and `/select` command handling
- mission intake classification and CODEX_CHAT update preview
- optional `planning/CODEX_CHAT.md` update only when explicitly enabled by env

## 3. Security Model

Required env vars:

- `CHARLIE_BUILD_RELAY_ENABLED`
- `CHARLIE_BUILD_RELAY_BOT_TOKEN`
- `CHARLIE_BUILD_RELAY_WEBHOOK_SECRET`
- `CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS`

Optional env vars:

- `CHARLIE_BUILD_RELAY_CODEX_CHAT_WRITE_ENABLED`
- `CHARLIE_BUILD_RELAY_REPO_ROOT`

The webhook secret must be at least 32 characters. Tokens and secrets must stay in `.env` or Render env vars only. They must not be committed, logged, exposed in frontend code, or copied into docs.

## 4. Authority Boundaries

CHARLIE Build Relay v0 cannot:

- run shell commands
- start Codex runtime by itself
- commit
- push
- merge
- deploy
- apply migrations
- write production Supabase data
- write Google Sheets data
- send customer messages
- publish public posts
- take payments/deposits
- reserve stock
- change pig lifecycle or purpose records
- bypass CODEX_CHAT hard stops

It can:

- answer owner-only Telegram commands
- summarize `CURRENT_STATE.md`
- list next mission candidates from `NEXT_STEPS.md`
- prepare mission intake from a Telegram message
- optionally write the mission into `planning/CODEX_CHAT.md` when the explicit write env flag is enabled

## 5. Owner Commands

Initial commands:

- `/help` - explain relay commands and safety
- `/status` - summarize current active repo state
- `/next` - show top mission candidates from `NEXT_STEPS.md`
- `/select 1` - turn a listed next-step option into a mission intake
- `/mission <idea>` - prepare a new mission intake

Unknown free text is treated as a mission idea, not as an instruction to execute dangerous work.

## 6. Recommended Rollout

### CHARLIE-RELAY-0 - Plan And Safe Skeleton

Status: this phase.

Scope:

- architecture/security plan
- disabled-by-default route
- owner allowlist
- webhook secret verification
- command parser
- tests

### CHARLIE-RELAY-1 - Notification Utility

Add a local script Codex can call after builds:

- send progress update
- send PR link
- send hard-stop alert
- send test/deploy summary

### CHARLIE-RELAY-2 - Owner Mission Intake

Enable Telegram `/mission` to write `CODEX_CHAT.md` in the approved runtime only.

For local Cursor/Codex work, this may be useful. For Render, repo filesystem writes are not durable mission infrastructure and should be replaced by Supabase mission records.

### CHARLIE-RELAY-3 - Supabase Mission Queue

Add durable mission records:

- mission id
- raw owner text
- parsed urgency/type/approval level
- status
- selected next-step source
- owner decisions
- debrief link

This requires a separate additive migration approval.

### CHARLIE-RELAY-4 - Approval Buttons

Add inline approval buttons for safe actions:

- continue planning
- run tests
- prepare PR
- pause
- reject

Dangerous actions still need explicit typed confirmation and the normal repo-side hard stops.

## 7. Tests

Current tests prove:

- policy is disabled by default
- no commit/merge/deploy/production-write authority exists
- webhook requires the Telegram secret header
- unlisted Telegram users are rejected
- `/next` sends button options
- `/mission` prepares intake without writing files by default
- CODEX_CHAT writes happen only when the explicit write flag is enabled

## 8. Remaining Risks

- Telegram can only drive Codex fully if a running Codex/Cursor process reads the mission file or a future durable mission queue.
- Render filesystem writes are not durable mission infrastructure.
- Supabase mission queue is the right next durable step, but it needs explicit migration approval.
- Inline approvals must not bypass the repo approval model.

## 9. GO / NO-GO

GO for CHARLIE Build Relay v0 as a safe disabled-by-default owner Telegram command layer.

NO-GO for autonomous merge/deploy/migration/customer/public/payment/reservation/lifecycle actions from Telegram.
