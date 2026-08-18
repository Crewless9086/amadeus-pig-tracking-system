# CHARLIE Build Relay Notification Stub

Last updated: 2026-07-11

This document covers the Mission Loop foundation notification stub. It is deliberately smaller than the full CHARLIE Build Relay: it formats and optionally sends status notifications, but it does not execute shell commands, merge PRs, send customer messages, run migrations, or call model APIs.

The private executive interface now uses the Render webhook as the primary single ingress. Local polling remains a diagnostic fallback and must not run against the same bot while its webhook is active. See `CHARLIE_PRIVATE_EXECUTIVE_INTERFACE.md`.

Local execution readiness is separately governed by `CHARLIE_CORE_RUNTIME_RECOVERY.md`. A successful Telegram response proves the command plane only; it does not prove the laptop CORE runtime, GitHub integration, or mission workforce is ready.

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

## Loop 7 Supabase Mission Control

`scripts/build_relay_telegram_buttons.py` adds the safe `/next` owner flow:

1. Owner sends `/next`.
2. The handler reads the Supabase `charlie_missions` owner queue first.
3. If Supabase is unavailable or empty, it falls back to `docs/00-start-here/NEXT_STEPS.md` and labels the fallback.
4. It sends the top five mission options as inline buttons.
5. Owner clicks one mission.
6. The callback resolves a compact token to the live Supabase `mission_id`, reloads current mission state, and opens an action card.
7. The card exposes only actions legal for that current state. Every write uses existing `mission_store` status/review functions and their compare-and-set protections.

Live Supabase selections do not write CODEX_CHAT. Fallback documentation options remain read-only; CODEX_CHAT is only an explicit manual/debug handoff.

The handler is testable through injected clients. Unit tests never send real Telegram messages.

## Hosted Mission Callback Round Trip

The Render webhook dispatches authenticated `cm:` mission-control callbacks to the same protected handler used by the local button flow before generic text-command handling. It claims the Telegram `update_id` in `charlie_inbound_updates` before a mission mutation and writes a sanitized terminal outcome (`processed`, `refused`, `ignored`, or `failed`) after handling. Authenticated non-owner callbacks are retained as ignored evidence; requests without the webhook secret are rejected before any durable record is created.

If completion of an already-claimed inbound update is unavailable, the relay returns the explicit `charlie_mission_callback_completion_failed` 503 outcome with the update key and does not retry either the completion call or the owner action. Completion updates only a `processing` row; if an expired incomplete claim is atomically closed as `failed` with `completion_unknown_replay_refused` first, a delayed completion returns a terminal conflict and cannot overwrite that evidence. Duplicate delivery distinguishes terminal rows from `processing`: a concurrent retry waits. Neither recovery path invokes the mission action again.

Final-release buttons include a compact token derived from the review packet's durable `review_generation`. The current generation and `pr_ready` status are compared in the mission update, so stale or duplicate review buttons fail closed. A successful owner callback receives the normal Telegram callback acknowledgement and refreshed mission card; the dashboard remains a read of the same authoritative mission record.

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
- `/status` shows relay, runner heartbeat, current agent, active mission, and queue counts.
- `/queue` shows current owner-queue missions.
- `/blocked` shows blocked missions.
- `/next` reads the live Supabase `charlie_missions` owner queue first and sends the top five actionable missions as buttons.
- Button selection opens a Supabase mission action card. New missions can be approved/paused/rejected; active missions are observe-only; blocked and review-ready missions can be returned through the existing review store; final approval remains owner-only.

## Always-On Local Relay

`scripts/install_charlie_telegram_relay_task.ps1` installs an opt-in Windows Scheduled Task that starts the relay at owner logon and restarts it after failures. The task runs only the relay process; it does not grant Telegram shell execution and does not start Codex.

The installed task now runs `charlie_telegram_relay_watchdog.py` through `pythonw.exe` every two minutes. The watchdog keeps the relay windowless, starts at most one listener, preserves a live lock, and removes a lock only when its recorded PID is dead. Relay stdout, stderr, and watchdog state remain under `.charlie_runner/` for diagnosis.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_charlie_telegram_relay_task.ps1
Start-ScheduledTask -TaskName "CHARLIE Telegram Relay"
```

The existing relay lock prevents a scheduled and manually-started relay from running together.

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

## Candidate-Bound Review Evidence

CORE release gates use `charlie_evidence_reconciliation_v1`. Every new agent artifact is bound to an immutable artifact ID, execution, candidate commit, candidate fingerprint, and frozen scope hash. Historical artifacts remain available for audit and ANALYST learning, but only the latest applicable artifact per agent can affect the current release decision.

- A resolved or superseded pre-build finding cannot override a later verified release candidate.
- A non-passing result for another commit or scope triggers a targeted recheck, not a generic full rerun.
- A current applicable failure remains a hard release blocker.
- Owner send-back preserves completed downstream stages whose candidate-bound evidence still applies; the runner skips those stages instead of spending another full pass.
- The owner review packet separates active blockers, resolved findings, follow-ups, and evidence requiring refresh, and records the exact candidate commit/fingerprint.
- Older missions without lineage retain the legacy gate until a targeted rerun creates candidate-bound evidence. No destructive database migration or history rewrite is required.

## CORE Infrastructure Holds

The runner may recover an interrupted Git operation only when the corresponding `rebase-merge` or `rebase-apply` marker directory exists and is completely empty. Non-empty Git operation metadata is never removed automatically. Before switching a mission branch back to the clean runner base, a changed generated `planning/CODEX_CHAT.md` is archived under `.charlie_runner/recovery/`.

Three identical deterministic runner failures, including base-branch checkout and runner-preflight failures, place the supervisor in `infrastructure_hold`. The owner receives one actionable notification, and the outer watchdog does not restart the same failure indefinitely. Resolve the recorded cause and explicitly restart CORE to clear the hold.

## Loop 8 Trust, Budget, And Model Routing Dry Run

`scripts/model_routing_plan.py` now produces deterministic routing recommendations. It does not import a provider SDK or make a model call. Every decision keeps `live_call_allowed=false`; red-zone work is blocked before model selection, and future activation must pass both the trust ledger and budget guard.

- GPT-5.6 Luna: future cheap triage, summaries, log compression, and low-risk classification.
- GPT-5.6 Terra: future balanced mission planning, normal PR review, and medium-risk guidance.
- GPT-5.6 Sol: future high-risk architecture, security, Supabase migration review, and repeated P0 failure analysis.

No Telegram action triggers GPT-5.6, Claude, Fable, GLM, OpenRouter, or any other model provider. Loop 8E live activation is deliberately not implemented.

## Duplicate Message Troubleshooting

Run only one relay process at a time. The local runner uses `.charlie_runner/telegram_relay.lock` to block a second process. If the relay is stopped with `Ctrl+C`, the lock is removed automatically.

If duplicate Telegram messages appear:

1. Stop the relay with `Ctrl+C`.
2. Check that no second `python scripts/charlie_telegram_relay.py` process is still running.
3. If no relay is running but `.charlie_runner/telegram_relay.lock` remains, remove that stale lock file.
4. Start the relay again.

Duplicate updates from Telegram should be skipped in-process by `update_id`, and duplicate button callbacks should be skipped by `callback_query.id`.
