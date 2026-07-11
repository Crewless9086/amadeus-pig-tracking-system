# CHARLIE Agent Workforce

## Purpose

`/charlie-agents` is the owner-only operational view for agent training, trust, dependencies, and graduation evidence. It complements `/charlie-v2`:

- Mission Control shows queued and running work.
- Agent Workforce shows who performs the work, which systems they depend on, and what evidence supports greater autonomy.

The dashboard composes existing sources. It is not a parallel agent registry, mission queue, or authority store.

## Authoritative Sources

- CHARLIE mission counts: Supabase `charlie_missions` through the mission store.
- SAM Live Stock learning: append-only conversation learning events and the live scorecard.
- Agent identity and role: `static/assets/agents/agent_registry.json`.
- Build trust: `loop/memory/trust.tsv` until a Supabase trust ledger replaces it.
- Runner state: the existing CHARLIE runner heartbeat contract.

Unavailable evidence is shown as `Not measured`. The UI must not invent a percentage.

## Percentage Meaning

SAM Live Stock's visible percentage is production-evidence progress:

- reviewed owner replies contribute 70%; target 100;
- complete conversations contribute 30%; target 20.

It is not an autonomous-send confidence score. Quality and safety gates still apply after the evidence floor is reached.

CHARLIE/Codex percentages come from verified trust-ledger runs when those records exist. Other agents remain `Not measured` until a real scorecard adapter exists.

## Graduation Notification

Graduation notification is enabled by default when the existing SAM Telegram token and owner chat ID are configured. Set `SAM_LIVE_STOCK_GRADUATION_NOTIFICATION_ENABLED=0` to disable it explicitly.

The notifier:

- evaluates only stored owner-reply evidence;
- writes an idempotent append-only notification marker;
- sends at most one first-crossing notification per reply class and graduation contract version;
- does not enable autoreply;
- does not change stock, orders, payments, reservations, or customer messages;
- requires an owner decision before any authority change.

It uses the existing SAM Telegram configuration:

- `SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN` or `OOM_SAKKIE_TELEGRAM_BOT_TOKEN`
- `SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID`

## Endpoints

- Page: `GET /charlie-agents`
- Evidence: `GET /api/charlie/agent-workforce`
- Forced refresh: `GET /api/charlie/agent-workforce?refresh=1`

The evidence response is cached for 30 seconds. Supabase mission and SAM scorecard reads run concurrently. Refreshing the UI keeps the current snapshot visible until the replacement succeeds.

## Safety Rule

Crossing a threshold creates an owner-review candidate only. No agent may approve itself, and no dashboard percentage may change production authority automatically.
