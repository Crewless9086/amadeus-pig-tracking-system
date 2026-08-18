# CHARLIE Private Executive Interface

## Purpose

CHARLIE is Charl's private executive AI interface. CHARLIE interprets owner intent, reads operational truth, delegates bounded CORE work, presents decisions, and reports outcomes. CORE remains the durable mission executor; Supabase remains authoritative.

This interface reduces owner workload without granting customer, money, stock, lifecycle, public-post, credential, destructive migration, or production-delete authority.

## Runtime Spine

1. Charl uses either the owner-only `/charlie` web interface or CHARLIE's dedicated Telegram bot. Telegram sends one signed webhook update to the Render ingress.
2. The ingress requires the configured owner user ID, owner private chat ID, and webhook secret.
3. `charlie_inbound_updates` claims the Telegram `update_id` before any reply or action.
4. The owner message and media metadata are stored in the active private conversation thread.
5. The adaptive executive runtime derives a durable goal and active subject, discovers governed capabilities, then creates a bounded evidence plan. Optional LLM classification or synthesis cannot grant authority.
6. Read questions may inspect several authoritative sources before CHARLIE replies. The response is composed only from successful tool evidence; failed reads are reported rather than guessed.
7. The authority policy permits reads, asks one clarification when context is insufficient, or creates an owner approval bundle for protected actions.
8. Typed write tools reload current CORE state, use compare-and-set transitions, and reload again to verify the outcome. Telegram cannot run shell commands.
9. The goal, active subject, plan, evidence status, pending follow-ups, intent, tool executions, and reply are stored durably in Supabase.

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
- Optional ElevenLabs speech requires `CHARLIE_PRIVATE_TTS_ENABLED=1`, `CHARLIE_PRIVATE_TTS_PROVIDER=elevenlabs`, `CHARLIE_PRIVATE_TTS_MODEL`, `CHARLIE_PRIVATE_TTS_VOICE_ID`, and `ELEVENLABS_API_KEY`. Browser speech synthesis remains the safe fallback.

## Supported Owner Commands

- `status`, `queue`, `blocked`, `brief`, `workforce`, `analyst`, `decisions`
- `business`, `sam`, `beacon`, `orders`, and `farm` provide typed read-only operating summaries.
- Ask about a mission by ID.
- Explicitly create a CORE mission.
- Explicitly approve, pause, reject, or send back a CORE mission.

Ambiguous commands produce one clarification. Attachments are recorded as metadata and never treated as instructions. Voice notes are transcribed only through the explicit private gate; raw audio is not persisted by CHARLIE.

Natural follow-ups such as `why?`, `what changed?`, `any update`, and `what happens next?` reuse the durable active mission or CORE context. Read-only inspection never requires owner permission.

## Executive Runtime v2: Phases A-B

- Durable conversation goal and active-subject state uses `charlie_conversation_threads.open_context_json`; it survives Render and runner restarts.
- Broad CORE and executive-brief questions use bounded multi-tool evidence plans instead of one classifier-to-one-template execution.
- CORE answers combine authoritative mission state, blocked-mission disposition, genuine owner decisions, and ANALYST evidence where relevant.
- Ordinary language cannot be treated as a mission ID unless it matches an explicit CHARLIE ID or contains a numeric identifier.
- Mission creates and transitions are not reported complete until current Supabase state verifies the outcome.
- CORE's existing executive cycle remains the only recovery supervisor. It performs policy-authorized, bounded internal recovery and durable escalation; the private runtime does not create a parallel controller.
- Render reports that it cannot see the laptop heartbeat instead of claiming the local runner is stopped. Supabase mission state remains visible.

## Executive Runtime v2: Phases C-E

### Phase C - Business Operations (implemented)

CHARLIE has typed cross-business reads for orders, SAM, Beacon, farm operations, workforce, ANALYST, trust, and CORE. A specific order ID can be inspected conversationally. An explicit order-pack instruction prepares and verifies the quote, loading sheet, removal certificate, and health declaration through the existing owner-gated sales-pack service. Beacon caption instructions use the existing historical-style and Meta-safety composer. Preparation never sends, posts, reserves, confirms payment, or changes livestock state.

### Phase D - Delegated Autonomy (implemented foundation)

Verified private write outcomes and owner bundle corrections feed `charlie_capability_trust`. Trust is visible through the private `trust` query and remains capability-specific. Existing promotion thresholds and executive delegation policies govern CORE internal recovery. Explicit yellow actions use current-state validation and post-write verification. Red-zone actions cannot be promoted or bypassed by trust, model output, or conversation text.

### Phase E - Voice And Proactive Operation (implemented)

Telegram voice notes use the existing size-limited transcription path and store no audio. The private web interface supports browser speech recognition where available. `Check ... in N minutes/hours` stores a durable follow-up in the conversation context. The supervised runner evaluates due follow-ups, gathers fresh authoritative evidence, and queues one idempotent private outbox message. Morning briefs now use the bounded multi-tool executive plan and the same durable retry/dead-letter outbox.

## Current Limits

- CHARLIE can prepare but cannot send a customer quote, publish or boost a Beacon post, confirm payment, reserve stock, or change animal lifecycle without the existing exact owner confirmation and domain executor.
- Browser speech availability depends on browser support and microphone permission. Telegram voice is the reliable mobile path when private transcription is enabled.
- Capability promotion is evidence-driven. New business actions start supervised and cannot be declared autonomous merely because implementation tests pass.
- New business modules still require a typed authoritative tool before CHARLIE may operate them. The runtime never uses generic shell access as a substitute.

## Approval Bundles

Non-delegated and red-zone requests become expiring approval records. A Telegram callback records approve, reject, or defer exactly once. Approval does not execute a business red-zone action. A later executor must reload state, validate the exact action, and use its domain-specific owner gate.

## Briefings

The first verified owner binding receives a default morning subscription at 06:30 Africa/Johannesburg. Due briefs enter the durable executive outbox once per local date and retain the existing retry/dead-letter behavior.

## Owner Interfaces

- `/charlie` is CHARLIE Live Executive: SSE-streamed runtime states, durable conversation, push-to-talk, server/browser transcription, provider/browser speech, stop/replay/mute, active commitments, structured evidence, and genuine owner decisions.
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

## Live Executive v1

`POST /api/charlie/private/message/stream` is the owner-admin SSE ingress. It emits owner-safe progress while the same private runtime gathers evidence and persists the turn. `POST /api/charlie/private/voice/transcribe` accepts size-limited owner audio; `POST /api/charlie/private/voice/speech` returns no-store speech audio only when the provider gate is configured. The browser falls back to Web Speech input/output when providers are unavailable. The response packet separates spoken summary, display answer, verified facts, recommendation, commitments, decisions, and source evidence.

Push-to-talk is explicit. Always-on listening is not enabled. Speech can be muted, stopped, replayed, or interrupted by the next owner turn.
