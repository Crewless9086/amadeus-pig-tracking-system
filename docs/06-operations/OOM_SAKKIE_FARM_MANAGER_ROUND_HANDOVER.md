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
