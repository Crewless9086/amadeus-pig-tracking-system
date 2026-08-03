# Oom Sakkie farm-manager round handover

Status: source correction in review; no production recovery performed by this document.

## Preserved acceptance evidence

- Telegram owner message: `3192`
- GateKeeper execution: `62039`
- relay execution: `62040`
- provider epoch: `1785734111`
- exact UTF-8 text SHA-256: `5a68bbe29ace54ca78e1d0a0beabff6270a4ecf44eefec008ca52ea0293fa21f`
- deployed tool: `irrigation_status`
- deployed answer: `Irrigation status could not be read from the irrigation sheet. Note: Irrigation is read-only here. No start/stop command was sent.`

The message is a genuine multi-domain request: herd welfare, breeding, weighing,
irrigation and general farm priorities. The narrow irrigation result is preserved
as defect evidence and must not be replayed.

## Source correction

`modules/oom_sakkie/farm_manager_runtime.py` introduces a provider-bound,
authenticated `farm_manager_round` contract. The existing Telegram gateway calls
it before specialist-specific and legacy intent handling. It invokes each
available specialist independently, reconciles only typed `SpecialistResult`
objects with the established farm-manager kernel, renders no more than three
actions and one question, and grants zero farm, weight, mating, customer,
publication or hardware authority. Missing or stale evidence remains a bounded
specialist gap.

The HERDMASTER projection is consolidated into one family action covering the
complete canonical Active/on-farm weighing worklist plus current breeding and
welfare priorities. Exact tag/Pig ID mappings remain in the authenticated
manager result for the existing governed bulk-weight preview/confirmation flow.
A genuine empty list is stated explicitly; a failed worklist read is a visible,
bounded HERDMASTER weighing gap. Completed Pig 125 work is suppressed and the
active Pig 11 lifecycle is retained without a duplicate question.

SAM and BEACON currently have no deployed typed manager-consumption adapter in
this source tree. Their conclusions therefore fail closed as bounded gaps; they
do not block supported HERDMASTER or ROOTLINE content and are not invented.
This is a declared limitation of the broader four-specialist farm-manager goal.

No second bot, router, queue, webhook or specialist Telegram path is added.

## Production proof required after reviewed integration

1. Prove exact deployed lineage and gateway health.
2. Acquire an unconsumed recovery guard bound to message `3192`, executions
   `62039/62040`, the content digest above, owner/chat, deployment and proof purpose.
3. Recover the preserved input once without replaying the legacy answer.
4. Require one provider-confirmed consolidated brief and persist its message identity.
5. Re-run the recovery and prove zero additional briefs, questions, cards or
   specialist work.
6. Verify zero farm/weight/mating/customer/publication/hardware effects.
7. Only if ROOTLINE reports immediate commissioning readiness, issue the separately
   governed readiness request; a new provider-timestamped physical-presence reply
   must be no older than five minutes before configuration or actuation.

Focused verification at the reviewed candidate: 556 tests passed with 7 skipped
across manager runtime/kernel, HERDMASTER runtime, Telegram routes/service,
health/loss and operational-specialist intake (plus 239 subtests). Independent
backend/security/privacy/authority review approved the corrected provider claim,
replay, precedence, delivery and zero-authority boundaries. Product/operations
review approval is required on the final exact head before integration.

Pig 125 completed work and other closed work are specialist lifecycle truth and
must remain suppressed. Pig 11 remains owned by its existing active lifecycle.

## 3 August production containment

PR #688 merged as `95e3431aa3e1a6f2ba9b0f6d1d22f39514b73a42`, all
exact-merge gates passed, and Render deployment `dep-d9o4asnlk1mc739khb2g`
became healthy at that exact commit. Recovery guard
`OOM-FARM-ROUND-3192-RECOVERY-95E3431A` was consumed once.

The manager result persisted successfully as
`OOM-FARM-ROUND-9DCAD5A9AAC677A90A92CCB0`, but the synchronous worker reached
its 30-second timeout while Telegram delivery was in flight. The durable family
lifecycle contains one delivery attempt and no authoritative delivered identity.
Provider delivery is therefore ambiguous: do not retry, resend or bind a guessed
message. Farm state remained outside the manager's zero-authority path.

The follow-up source correction runs independent read-only specialist loaders
concurrently and constrains rendered Telegram text to 3,900 characters. This
restores delivery budget generically; it does not authorize replay of the
ambiguous 3192 attempt. A later fresh owner manager request is the next safe live
acceptance case unless authoritative provider chronology first proves the exact
3192 delivery identity.

The corrected delivery-budget candidate passed 560 focused tests with 7 skipped
and 239 subtests. Independent operations/CX and backend/security/privacy/
authority reviewers approved the shared max-eight specialist bulkhead, bounded
deadline, typed partial containment, escaped-length HTML budgeting and immutable
3192 non-retry decision.

## P0 owner-context continuation correction

Message `3192` and its consumed recovery guard remain immutable and must never be
retried. The next source correction addresses a distinct, genuine lifecycle:

- Telegram `3202`, relay `62062`, mission
  `OOM-HERDMASTER-368E7C97C6D82C2416716A19`, Pig 127 / `PIG-2026-D13C`;
- Telegram `3204`, relay `62064`, retained urgent follow-up digest
  `8cbb0a71c12703513b8085cf22348a83018cb8129ab64550b784845994b26aa1`;
- Telegram `3206`, relay `62066`, retained entity clarification digest
  `257c015b5d477340a5b54873c0d8ee6f632541edc781bd912d1039315680f64a`.

The authenticated gateway now preserves reply-to identity and resolves owner
conversation in this order within the health lifecycle: exact confirmation,
exact card reply, explicit animal identity, then the uniquely newest pending
owner question. Multiple genuinely possible cases produce one visible typed
disambiguation and retain the inbound digest instead of returning a generic
backend rejection. A bare entity clarification is durably retained while the
existing lifecycle card and question remain unchanged. Authenticated owner text
that reaches no supported specialist is retained by a zero-authority owner front
door with one useful farm-context clarification; the legacy V1 fallback is no
longer an owner-facing operational result.

The natural welfare evaluator distinguishes positive, negative and Unknown
physical evidence. Pig 127's preserved follow-up supports owner-reported inability
to stand, apparent inability to drink or function normally, and the owner's
assessment that the pig appeared close to death. Those are observations, not a
diagnosis or cause. Breathing remains the one smallest Unknown observation.
Nothing in this source correction grants farm-write or treatment authority.

### Exact later production proof

1. Integrate and deploy only an independently reviewed exact head and verify its
   exact merge/deployment lineage.
2. Use distinct unconsumed recovery guards for `3204` and `3206`; never alter the
   `3192` guard.
3. Recover `3204` once into the existing Pig 127 mission and existing card. Require
   immediate proportional welfare guidance and one breathing-only question, with
   zero farm rows.
4. Recover `3206` once as clarification evidence. Require zero additional card,
   question or message and prove both guard replays create zero rows, sends, edits,
   missions and work items.
5. Release runtime while awaiting Charl. A later authenticated answer must produce
   the consolidated preview; only its exact authenticated confirmation may invoke
   the existing governed HERDMASTER writer.
6. For Proof B, wait for a new genuine manager request. Do not replay `3192`.
   Require provider-confirmed delivery of one bounded HERDMASTER/ROOTLINE brief,
   at most three actions and one question, honest SAM/BEACON availability and zero
   protected actions.

Prepared inputs remain governed and unconsumed until the matching manager path
is ready: ROOTLINE packet
`ROOTLINE_POST_P0_COMMISSIONING_AND_DAILY_HANDOVER_20260803.md` at SHA-256
`BC41AE22FE897C96769E949888C1258157A293B401931737D340D9039D62D4C7`, and
unmerged HERDMASTER PR `#690` at exact head
`0b77f10b346f1f0a4a9ee181ec708d43e8e9ffd6`. The ROOTLINE packet is read-only
specialist evidence. Its commissioning procedure remains a separately protected
decision and grants no irrigation or hardware authority.

### Later acceptance requirements (not blockers for this P0 proof)

- Charl retains the authenticated owner and protected-decision authority.
- Mom and Dad require distinct authenticated identities and explicitly scoped
  permissions before their messages can enter governed owner lifecycles.
- Natural Afrikaans and English must use the same context, evidence, preview,
  confirmation, replay and authority rules. Family members must never have to
  translate observations into English or complete a rigid form.

## P0 Proof B material correction

The next genuine owner request is authoritatively bound to Telegram inbound
`3208`, GateKeeper execution `62102`, relay execution `62103`, provider epoch
`1785753983`, content SHA-256
`5f6f1459ebdd83f241a4a038f3e4a10cdfbb13c82b781d559b0fef2ff081d471`,
manager mission `OOM-FARM-ROUND-0FCB0C799AFC160886B57077`, and delivered daily
card `3209`. The first v1 result is preserved as defect evidence: it had zero
actions and globally rendered `BOUNDED WAITING` from section-local specialist
limitations.

The v2 composition contract permits one material recomposition only when the
same exact provider binding owns that v1 zero-action defect. It stores the v2
result as a new immutable revision under the same mission and lets the existing
family lifecycle edit card `3209`; an ordinary same-version replay remains a
no-op. Missing, stale, unavailable and contained specialists remain typed in the
internal result but are suppressed from family-facing text. A specialist with
no owner action is also suppressed.

HERDMASTER consumption uses the reviewed whole-herd packet contract from merged
PR `#690`. The prepared production result ranks the existing Pig 127 welfare
question first, then groups Mona and Mysikind's proportional farrowing
preparation with the Monday weighing journey. The authenticated 1 August owner
observation is Telegram `3151`, GateKeeper execution `61664`, provider timestamp
`2026-08-01T11:51:04+00:00`, and SHA-256
`c19f2c2b9e3088c49a051b5f76d5d92b6339e7539349c0892e097ee3bd7b3735`.
It supports operational `Assumed Pregnant` for Mona and Mysikind and
`Inconclusive` for Baby; it is not clinical confirmation and grants no write.
An existing active welfare lifecycle is deduplicated by Pig ID and card rather
than becoming a new case or question.

ROOTLINE refresh is independently time-bounded. If a fresh safe recommendation
cannot be built inside the manager deadline, its section contributes only a
plain practical reassessment action and observation request; it never exposes
runtime or containment language and grants no irrigation or commissioning
authority. SAM's supported zero-action state and BEACON's absent owner-relevant
work are suppressed.

Focused source verification: `829 passed, 7 skipped, 351 subtests passed` across
all Oom Sakkie tests. The exact reviewed head still requires normal CI,
integration, exact-merge CI and exact deployment lineage.

Independent farm-operations/CX and backend/security/privacy/authority reviews
approved the final candidate after verifying section-local reproductive
suppression, strict current-mating/timestamp provenance, one durable
recomposition winner, bounded loaders, existing-card editing and zero authority.

### Exact Proof B production proof

1. Revalidate inbound `3208`, executions `62102/62103`, card `3209`, provider
   timestamp/digest, authenticated owner/chat and exact deployed lineage.
2. Bind the three Telegram `3151` pregnancy observations as read-only manager
   evidence with exact Pig/mating identities. This must change zero farm rows.
3. Recover `3208` once under a distinct unconsumed correction guard. Require one
   authoritative in-place edit of card `3209`, zero new Telegram messages, no
   duplicate lifecycle/question, and no protected action.
4. Require the corrected card to begin with Pig 127's existing breathing
   observation, contain no more than three supported actions and one question,
   include the supported HERDMASTER work and a proportional ROOTLINE result,
   and contain none of the suppressed internal failure terms.
5. Repeat the exact recovery and require zero packets, revisions, sends, edits,
   questions, missions, commands or farm rows.
6. Verify Pig 127 remains in its canonical zero-write lifecycle, message `3192`
   remains quarantined, and all unrelated specialist and protected state is
   unchanged. Release the serialized runtime immediately.

Proof B is business-complete only after Telegram provider evidence proves Charl
can see the corrected useful card. Source, CI, merge, deployment or containment
alone is insufficient.
