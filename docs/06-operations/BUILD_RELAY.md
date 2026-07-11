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

