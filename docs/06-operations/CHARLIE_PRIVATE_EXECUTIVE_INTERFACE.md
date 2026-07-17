# CHARLIE Private Executive Interface

## Purpose

CHARLIE is Charl's private executive AI interface. CHARLIE interprets owner intent, reads operational truth, delegates bounded CORE work, presents decisions, and reports outcomes. CORE remains the durable mission executor; Supabase remains authoritative.

This interface reduces owner workload without granting customer, money, stock, lifecycle, public-post, credential, destructive migration, or production-delete authority.

## Runtime Spine

1. Charl uses either the owner-only `/charlie` web interface or CHARLIE's dedicated Telegram bot. Telegram sends one signed webhook update to the Render ingress.
2. The ingress requires the configured owner user ID, owner private chat ID, and webhook secret.
3. `charlie_inbound_updates` claims the Telegram `update_id` before any reply or action.
4. The owner message and media metadata are stored in the active private conversation thread.
5. The planner emits one typed intent. Deterministic commands are preferred; optional LLM classification is disabled unless its complete configuration is present.
6. The authority policy either permits a read/bounded CORE action, asks a clarification, or creates an owner approval bundle.
7. Typed tools reload current CORE state and use compare-and-set transitions. Telegram cannot run shell commands.
8. The result, intent, tool execution, and CHARLIE reply are stored durably.

## Configuration

Required:

- `CHARLIE_PRIVATE_EXECUTIVE_ENABLED=1`
- `CHARLIE_PRIVATE_TELEGRAM_BOT_TOKEN`
- `CHARLIE_PRIVATE_TELEGRAM_WEBHOOK_SECRET` (at least 32 characters)
- `CHARLIE_PRIVATE_TELEGRAM_OWNER_USER_ID`
- `CHARLIE_PRIVATE_TELEGRAM_OWNER_CHAT_ID`

The private variables may temporarily fall back to the existing Build Relay bot token, secret, and first allowed owner ID. Production operation must use a dedicated private bot so CORE cannot compete with CHARLIE for the same updates or flood the owner channel.

Optional:

- `CHARLIE_CORE_NOTIFICATION_MODE=executive_only` suppresses routine running/done chatter while preserving genuine owner decisions.
- `CHARLIE_TELEGRAM_TRANSPORT=webhook` prevents the legacy local polling relay and watchdog from starting against the webhook-managed bot.
- Private LLM classification requires `CHARLIE_PRIVATE_LLM_ENABLED=1`, a valid `CHARLIE_PRIVATE_LLM_MODEL`, and `OPENAI_API_KEY`. Model output never grants authority.
- Voice transcription requires `CHARLIE_PRIVATE_TRANSCRIPTION_ENABLED=1`, `CHARLIE_PRIVATE_TRANSCRIPTION_MODEL`, and `OPENAI_API_KEY`. Audio is downloaded in memory, size-limited, transcribed, and not persisted by CHARLIE.

## Supported Owner Commands

- `status`, `queue`, `blocked`, `brief`, `workforce`, `analyst`, `decisions`
- `business`, `sam`, `beacon`, `orders`, and `farm` provide typed read-only operating summaries.
- Ask about a mission by ID.
- Explicitly create a CORE mission.
- Explicitly approve, pause, reject, or send back a CORE mission.

Ambiguous commands produce one clarification. Attachments are recorded as metadata and never treated as instructions. Voice notes are transcribed only through the explicit private gate; raw audio is not persisted by CHARLIE.

## Approval Bundles

Non-delegated and red-zone requests become expiring approval records. A Telegram callback records approve, reject, or defer exactly once. Approval does not execute a business red-zone action. A later executor must reload state, validate the exact action, and use its domain-specific owner gate.

## Briefings

The first verified owner binding receives a default morning subscription at 06:30 Africa/Johannesburg. Due briefs enter the durable executive outbox once per local date and retain the existing retry/dead-letter behavior.

## Owner Interfaces

- `/charlie` is the private executive cockpit: durable conversation, business/CORE status, evidence metrics, approved preferences, and genuine owner decisions.
- `/charlie-v2` remains CORE engineering control and detailed mission evidence. It is not the normal owner inbox.
- `/charlie-agents` remains workforce readiness and training evidence.
- Routine CORE stage events do not contact Charl in `executive_only` mode. Only deduplicated owner decisions and hard stops may surface through CHARLIE.

## Rollback

Set `CHARLIE_PRIVATE_EXECUTIVE_ENABLED=0`. The existing Build Relay webhook handler resumes without deleting private history. Set `CHARLIE_CORE_NOTIFICATION_MODE=all` to restore legacy notification volume. No rollback requires data deletion.

## Acceptance Standard

- One authenticated Telegram update produces at most one action and one reply.
- Unauthorized users and group chats receive no operational data.
- Ambiguous intent cannot mutate state.
- Every allowed write uses current state and compare-and-set protection.
- Red-zone execution from this runtime remains zero.
- Required deterministic tests pass before deployment.
