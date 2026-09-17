# Oom Sakkie LLM Semantic Front Door

## Business outcome

Charl and authenticated family users may speak naturally to Oom Sakkie in
English or Afrikaans. Oom Sakkie uses an LLM to understand meaning and current
conversation context before selecting HERDMASTER, ROOTLINE, SAM, BEACON, the
farm-manager round, or one clarification.

This replaces the former Telegram `deterministic_only` boundary. It is not a
larger regex library and does not create phrase-specific execution paths.

## Authority boundary

The LLM interprets only. It cannot:

- write farm, health, lifecycle, mating, weight or customer records;
- send customers or publish media;
- operate irrigation or other hardware;
- approve protected decisions;
- retry ambiguous external effects.

Existing authenticated specialist adapters, exact previews, confirmations,
idempotency identities, chronology checks and action rails remain authoritative.

## Context contract

The model receives only the current authenticated message plus bounded context:

- reply-to identity;
- at most eight active HERDMASTER case summaries;
- at most eight recent Oom Sakkie specialist-card summaries.

It does not receive full customer conversations, full animal records, secrets,
credentials or unrestricted database content.

## Typed result

The allowlisted domains are `herd_health`, `rootline`, `manager_round`, `sam`,
`beacon`, and `general`. The result carries intent, bounded entity references,
continuation status, a concise normalized observation, requested action,
language, confidence and at most one clarification.

Malformed JSON, unknown domains, provider errors and timeouts fail back without
granting authority. Exact callbacks and confirmations remain deterministic.

## Required production configuration

- `OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED=1`
- `OOM_SAKKIE_LLM_ROUTER_MODEL=<approved model>`
- `OPENAI_API_KEY=<configured secret>`
- optional `OOM_SAKKIE_LLM_ROUTER_URL`
- optional bounded `OOM_SAKKIE_LLM_ROUTER_TIMEOUT_SECONDS`

## Acceptance journeys

- `Pig 127 is dead; he did not make it and he is buried now.` routes as new
  HERDMASTER mortality evidence, not the old breathing question.
- `Vark 127 is dood; hy het dit nie gemaak nie en ons het hom begrawe.` has the
  same typed meaning.
- `C Camp has stopped` routes as ROOTLINE shutdown evidence, not the legacy
  irrigation-sheet status lookup.
- `C-kamp het gestop` has the same typed meaning.
- short follow-ups use active/recent specialist context.
- a natural request for today's farm priorities invokes the manager round.
- replay, confirmation and action authority remain deterministic.

Production proof must verify one genuine English or Afrikaans owner message,
provider-confirmed response delivery, correct specialist ownership, no
unrequested farm/hardware/customer effect, and unchanged replay.
