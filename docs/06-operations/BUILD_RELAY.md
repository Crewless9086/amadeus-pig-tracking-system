# CHARLIE Build Relay Notification Stub

Last updated: 2026-07-11

This document covers the Mission Loop foundation notification stub. It is deliberately smaller than the full CHARLIE Build Relay: it formats and optionally sends status notifications, but it does not execute shell commands, merge PRs, send customer messages, run migrations, or call model APIs.

## Environment

Primary env names:

- `CHARLIE_BUILD_RELAY_ENABLED`
- `CHARLIE_BUILD_RELAY_BOT_TOKEN`
- `CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS`

Existing legacy relay variables may still exist elsewhere in CHARLIE. Do not introduce token drift: if aliases are added later, document them here and keep the script's primary names stable.

## Statuses

`scripts/build_relay_notify.py` supports:

- `RUNNING`
- `DONE`
- `PR_READY`
- `DEPLOYED_NEEDS_TEST`
- `FAILED_TESTS`
- `HARD_STOP`
- `NEEDS_OWNER_APPROVAL`
- `BUDGET_STOP`

## Safety Behavior

- Disabled relay does nothing and returns success.
- Enabled relay without token or allowed user IDs fails safely.
- Tests inject a fake sender and never require a real Telegram token.
- Notification bodies redact common token/API-key shapes.
- No secrets are printed intentionally.
- No real Telegram send happens unless the relay is explicitly enabled and configured.

## Usage

Local dry/no-op example:

```powershell
python scripts/build_relay_notify.py DONE --mission-id MISSION-123 --title "Foundation complete"
```

Enabled production usage is a later owner-approved layer. This foundation only proves the format, redaction, and guard behavior.

## Mission Source Of Truth

CHARLIE CORE and Supabase `charlie_missions` are the primary mission system. Telegram relay features must control or inspect that mission state instead of creating a second file-first workflow.

- `/next` reads the live Supabase owner queue first.
- `docs/00-start-here/NEXT_STEPS.md` is fallback/planning only when Supabase is unavailable or empty.
- `planning/CODEX_CHAT.md` is manual/local/debug handoff only.
- Loop 7A must move Telegram callbacks to Supabase `mission_id` action cards. New primary features must not write CODEX_CHAT as their normal path.

## Loop 5 Button Flow

`scripts/build_relay_telegram_buttons.py` adds the safe `/next` owner flow:

1. Owner sends `/next`.
2. The handler reads the Supabase `charlie_missions` owner queue first.
3. If Supabase is unavailable or empty, it falls back to `docs/00-start-here/NEXT_STEPS.md` and labels the fallback.
4. It sends the top five mission options as inline buttons.
5. Owner clicks one option.
6. Current transitional behavior writes a manual `planning/CODEX_CHAT.md` handoff through `scripts/codex_next_steps.py`.
7. The bot sends a confirmation.

This layer still does not run Codex, start a scheduler, merge PRs, call model APIs, or perform production data writes. The CODEX_CHAT write is a transitional manual handoff, not the future primary mission-control path.

The handler is testable through injected clients. Unit tests never send real Telegram messages.

## Loop 6 Local Live Relay

`scripts/charlie_telegram_relay.py` is the local smoke runner for `@CharlieCoreBot`.

Required env:

```powershell
$env:CHARLIE_BUILD_RELAY_ENABLED = "1"
$env:CHARLIE_BUILD_RELAY_BOT_TOKEN = "<telegram bot token>"
$env:CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS = "<owner telegram user id>"
```

Run once without real sends:

```powershell
python scripts/charlie_telegram_relay.py --once --dry-run
```

Run local polling:

```powershell
python scripts/charlie_telegram_relay.py
```

Supported commands:

- `/start` confirms the relay is online.
- `/status` shows relay safety status.
- `/next` reads the live Supabase `charlie_missions` owner queue first and sends the top five actionable missions as buttons.
- Button selection currently writes a manual `planning/CODEX_CHAT.md` handoff and confirms. Loop 7A replaces this with Supabase `mission_id` action cards.

Safety boundaries:

- only configured owner user IDs are allowed;
- disabled relay exits safely;
- enabled relay without token/user IDs fails safely;
- token is read from env only and redacted from output;
- polling advances Telegram offset to the highest processed `update_id + 1`;
- the running process remembers processed `update_id` and `callback_query.id` values so duplicate Telegram delivery does not duplicate messages;
- callback queries are acknowledged once with `answerCallbackQuery`;
- a local lock file prevents accidentally running two relay processes at the same time;
- no shell commands run;
- Codex is not started;
- no model APIs are called;
- no scheduler, auto-merge, production data write, or customer send is enabled.

If Supabase is unavailable or the live owner queue is empty, `/next` falls back to `docs/00-start-here/NEXT_STEPS.md` and labels the message as `Source: fallback docs menu`. The fallback is only a backup; the live mission queue is the preferred source of truth.

## GPT-5.6 Family Alignment

GPT-5.6 routing is planned but disabled. Sol, Terra, and Luna are future support modules behind the budget gate and trust ledger. Loop 6.5 performs alignment only; no live model calls are allowed.

- GPT-5.6 Luna: future cheap triage, summaries, log compression, and low-risk classification.
- GPT-5.6 Terra: future balanced mission planning, normal PR review, and medium-risk guidance.
- GPT-5.6 Sol: future high-risk architecture, security, Supabase migration review, and repeated P0 failure analysis.

No Telegram action triggers GPT-5.6, Claude, Fable, GLM, OpenRouter, or any other model provider in Loop 6.5. Future model calls must pass the budget gate, trust ledger, owner authority rules, and the final verify gate.

## Duplicate Message Troubleshooting

Run only one relay process at a time. The local runner uses `.charlie_runner/telegram_relay.lock` to block a second process. If the relay is stopped with `Ctrl+C`, the lock is removed automatically.

If duplicate Telegram messages appear:

1. Stop the relay with `Ctrl+C`.
2. Check that no second `python scripts/charlie_telegram_relay.py` process is still running.
3. If no relay is running but `.charlie_runner/telegram_relay.lock` remains, remove that stale lock file.
4. Start the relay again.

Duplicate updates from Telegram should be skipped in-process by `update_id`, and duplicate button callbacks should be skipped by `callback_query.id`.
