# Oom Sakkie generic family-message lifecycle handover

## Outcome

The existing authenticated Telegram gateway now owns visible delivery for
ordinary family messages. It no longer depends on the inert caller-send tail
that caused authenticated message 3169 to disappear after safe validation.
No second bot, trigger, router, queue or specialist service is introduced.

Each message is bound to owner, private chat, provider message/time,
responsible specialist and a deterministic mission. The lifecycle persists a
delivery attempt before provider I/O, requires a Telegram message identity,
suppresses duplicate updates and edits the same card when a natural follow-up
advances the same specialist mission. An interrupted attempted delivery is
contained rather than blindly retried. A missing adapter produces one truthful
buttonless exception and never claims deployed-agent work.

## HERDMASTER health/welfare path

The merged PR #651 evaluator is the first specialist adapter. It resolves the
canonical animal, retains later natural language in the open context, asks at
most one smallest question, and produces one consolidated preview. Observed
facts, owner suspicion, veterinary attribution and agent inference remain
separate.

Explicit confirmation must be exactly `CONFIRM <operation_id>` from the same authenticated owner bound into the preview. Completed context remains loadable only for that exact confirmation replay; unrelated later text cannot reopen it. The writer
revalidates the canonical evidence generation and uses the existing append-only
`pig_observation_events` rail transactionally. The deterministic operation ID
is the idempotency key, so direct replay creates zero rows. This bounded writer
supports exactly one factual `medical_observation` effect. Multiple supported effects, including multiple medical observations, fail closed rather than producing a partial write. If a preview also proposes
lifecycle, mating, litter, movement, availability or downstream effects, it
fails closed with `canonical_effect_coordinator_unavailable`; supported
read-only welfare guidance and preview remain available.

## Pig 11 continuation

Messages 3169 and 3171 are immutable recovery evidence and must not be replayed
or resent. Production continuation must:

1. verify provider chronology and absence of a later welfare reply;
2. verify card 3171 against authoritative provider evidence for the exact bot, chat, message identity and text digest, then bind it to the deterministic generic mission with zero send;
3. seed the open PR #651 context from the authenticated report without a farm
   write;
4. accept only a later authenticated natural reply;
5. edit card 3171 into the resulting clarification/preview;
6. wait without holding runtime if no reply exists;
7. record only after exact preview confirmation, prove replay writes zero rows,
   refresh HERDMASTER evidence and edit card 3171 to the result.

## Required proof

- exact source/merge/deployment lineage;
- authenticated private-owner message produces one provider-confirmed visible
  lifecycle result;
- repeated provider update produces zero sends, edits and rows;
- later natural context does not repeat known facts;
- stale/conflicting evidence blocks only recording;
- process interruption creates no blind retry;
- exactly confirmed factual recording creates one row; replay creates zero;
- SAM Level 1, ROOTLINE containment, BEACON measurement, CORE/CHARLIE and
  unrelated claims/configuration remain unchanged.

