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

## Loop 5 Button Flow

`scripts/build_relay_telegram_buttons.py` adds the safe `/next` owner flow:

1. Owner sends `/next`.
2. The handler reads `docs/00-start-here/NEXT_STEPS.md`.
3. It sends the top five P0/P1/P2 mission options as inline buttons.
4. Owner clicks one option.
5. The selected option is written to `planning/CODEX_CHAT.md` through `scripts/codex_next_steps.py`.
6. The bot sends a confirmation.

This layer still does not run Codex, start a scheduler, merge PRs, call model APIs, or perform production data writes. It only prepares the active mission file.

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
- `/next` sends the top five missions from `NEXT_STEPS.md` as buttons.
- Button selection writes the chosen mission into `planning/CODEX_CHAT.md` and confirms.

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

## Duplicate Message Troubleshooting

Run only one relay process at a time. The local runner uses `.charlie_runner/telegram_relay.lock` to block a second process. If the relay is stopped with `Ctrl+C`, the lock is removed automatically.

If duplicate Telegram messages appear:

1. Stop the relay with `Ctrl+C`.
2. Check that no second `python scripts/charlie_telegram_relay.py` process is still running.
3. If no relay is running but `.charlie_runner/telegram_relay.lock` remains, remove that stale lock file.
4. Start the relay again.

Duplicate updates from Telegram should be skipped in-process by `update_id`, and duplicate button callbacks should be skipped by `callback_query.id`.
