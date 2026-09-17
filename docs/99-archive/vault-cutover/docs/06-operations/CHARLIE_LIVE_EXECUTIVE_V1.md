# CHARLIE Live Executive v1

## Outcome

CHARLIE Live Executive is Charl's private, real-time conversation surface over the existing governed executive runtime. Dashboard, Telegram, and voice share Supabase conversation state, capability evidence, authority policy, commitments, and owner decisions. This feature does not create another agent or mission system.

## Runtime Events

The owner web stream may emit:

- `turn_started`
- `intent_understood`
- `capability_started`
- `evidence_received`
- `reply_ready`
- `turn_completed`
- `turn_failed`

Every event carries a turn ID and owner-safe detail. Tokens, prompts, raw secrets, stack traces, and unrestricted backend payloads are forbidden.

## Executive Response Contract

```json
{
  "spoken_summary": "Short natural answer for speech",
  "display_answer": "Complete concise executive answer",
  "verified_facts": [],
  "recommendation": "",
  "actions_taken": [],
  "commitments": [],
  "owner_decision": null,
  "evidence": [],
  "active_subject": {},
  "confidence": 0.0
}
```

Speech uses `spoken_summary`; evidence and decisions remain visible. A model may phrase verified evidence but cannot grant authority or mark actions complete.

## Voice Contract

- Push-to-talk is explicit; always-on listening is disabled.
- Browser speech recognition and speech synthesis are fallbacks.
- Server transcription and ElevenLabs speech are optional, environment-gated providers.
- Failed providers fall back to typed input or browser speech without losing the conversation.
- Mute, stop, replay, transcript review, and interruption are owner controls.

## Decision Contract

Decision cards must show the requested action, affected mission/order/conversation/customer when present, recommendation, expiry, and the fact that execution revalidates current state. Generic or targetless protected actions cannot be approved.

## Safety

Read investigation is automatic. Customer sends, public posts, payments, reservations, lifecycle/purpose writes, destructive migrations, credentials, and production deletion remain owner-gated. CORE remains the engineering workforce; CHARLIE does not write code.

## Release Gate

- streaming event order and terminal event tested;
- duplicate updates remain idempotent;
- voice endpoints require owner admin access and configured providers;
- secrets never appear in policy or event output;
- interruption, mute, replay, and text fallbacks work;
- desktop and mobile show no overlapping controls;
- all CHARLIE and repository verification tests pass;
- Render deployment and owner-only live canary verified.

## Deployment Evidence

On 2026-07-18 the Render SSE canary authenticated through the owner session and emitted `turn_started`, `intent_understood`, two `capability_started`, two `evidence_received`, `reply_ready`, and `turn_completed`. The terminal packet was `charlie_live_executive_response_v1`, contained a spoken summary and two authoritative evidence rows, and reported complete evidence for the canary question.
