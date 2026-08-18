# HERDMASTER Breeding Exposure, Recovery Hold, and Unknown-Parent Plan

Status: **Owner-approved, deferred mission. Not implemented.**

Approved by Charl on 2026-08-12. HERDMASTER must finish and release its current deployment work first. Before this mission starts, reconcile the latest feedback and ownership from all specialist terminals and verify that the serialized production lane is free.

## Owner-visible business outcome

Charl and his father can record what physically happened without inventing a mating or conception date; an under-condition sow remains visibly held until fresh recovery evidence clears her; and a sow that is already near farrowing can produce a valid litter even when the historical mating date and father are unknown.

The completed journey must work through both the application and Oom Sakkie's authenticated Telegram path, using the same canonical facts and the same protected preview/execution rules.

## Approved farm operating truth

- Physical placement with a boar for the farm's planned 17-day exposure is not proof of the precise service or conception date.
- Heat observation is not a routine prerequisite for planned placement.
- A weaned sow whose current body condition is 2 or lower must not remain in the actionable mating group.
- Time passing does not prove recovery. A fresh attributable observation and an explicit governed clearance are required before the sow returns to mating recommendations.
- The initial proposed operational release threshold is body condition 3 or better, subject to owner confirmation during implementation. The system must preserve the actual score and must not infer it.
- An observed near-farrowing sow must not be assigned to a new boar merely because the earlier mating record is absent.
- Unknown historical mating date and unknown father are valid facts. Neither may be guessed or manufactured.

## Current real-world cases that define acceptance

### Ms Piggy

- Current owner observation: body condition 2.
- She was not suitable for the proposed immediate placement.
- Required state: recovery hold with the factual reason and observation date.
- She must disappear from actionable placement recommendations until a fresh observation supports recovery and the hold is explicitly cleared.

### Linda

- Current owner observation: she appears close to farrowing.
- Historical mating date: Unknown.
- Father: Unknown.
- She must be removed from the current mating cohort without inventing a mating or sire.
- When farrowing genuinely occurs, the normal litter workflow must accept Linda as mother, father Unknown, mating date Unknown, and the actual Jong Datum and litter facts.

## Required canonical model

Keep these facts separate:

1. **Recommendation** — advisory sow/boar choice only.
2. **Planned placement** — intended future action, not performed.
3. **Boar exposure** — actual placement start, actual or planned removal/end, sow, boar, provenance and status.
4. **Observed service/mating** — only when attributable evidence supports it.
5. **Conception/pregnancy state** — never inferred from exposure alone.
6. **Recovery hold** — current reason, evidence, effective time and clearance state.
7. **Farrowing/litter** — actual outcome; may retain Unknown mating date and Unknown father.

Do not overload the existing mating date with an exposure start if its contract asserts an exact service. Prefer a governed exposure record or extend the canonical model without creating a competing ledger.

## Application journey

- Provide one grouped placement/exposure capture for the sows and boars physically grouped on a date.
- Show the exact sow, boar, placement start and planned 17-day window in one preview.
- Allow individual exclusions in the same workflow, including recovery hold and already-pregnant/near-farrowing evidence.
- Show current recovery holds prominently on Breeding Attention and exclude them from actionable recommendations.
- Require fresh observation plus explicit clearance; never auto-release a hold due only to elapsed time.
- Allow litter creation with an Unknown father and Unknown historical mating without degrading or duplicating the litter.
- After a genuine farrowing, supersede stale mating-candidate attention automatically from canonical litter evidence.

## Telegram journey

Oom Sakkie must accept one natural grouped report containing:

- actual sow-boar placements;
- the placement date and planned exposure duration once;
- sows not placed and the factual reason;
- a recovery hold observation;
- a near-farrowing observation with unknown historical mating/father.

It must return one concise grouped preview. The preview must include every supplied sow exactly once, separate placements from holds, retain Unknown facts, and create nothing before protected confirmation. Prefer short Afrikaans confirmation buttons where the protected-action rail supports them.

If the grouped input is only partly understood, Oom Sakkie must not record the understood subset as the full group. It should ask at most one precise grouped clarification.

## Recommendation refresh

HERDMASTER must refresh the practical breeding worklist after any attributable:

- exposure placement or removal;
- body-condition observation;
- recovery hold or clearance;
- pregnancy/farrowing observation;
- litter creation;
- weaning completion.

The refreshed list must exclude held, pregnant/near-farrowing and nursing females; retain genuine uncertainty; and explain any changed cohort without treating missing evidence as readiness.

## Migration and preservation rules

- Preserve existing mating, litter, observation and recommendation history.
- Do not rewrite earlier recommendations as though Ms Piggy or Linda had already been excluded.
- Do not create a historical Linda mating or identify a father without evidence.
- Do not turn exposure into confirmed mating, pregnancy or conception.
- Use append-only correction/supersession where existing facts genuinely require correction.
- Do not introduce a second mating, litter, observation or recommendation ledger.

## Real-world acceptance

This mission is not complete at source-ready, CI, merge, deployment, replay, containment or handover.

Completion requires fresh end-to-end proof that:

1. A genuine grouped report records every actual exposure exactly once with no invented exact service date.
2. Ms Piggy, or an equivalent real sow with current body condition 2 or lower, is held and removed from actionable recommendations.
3. A later fresh recovery observation and explicit clearance can return the sow to consideration without overwriting history.
4. Linda, or an equivalent genuine case, can have a litter recorded with father and historical mating date Unknown.
5. The refreshed breeding worklist reflects all four outcomes correctly.
6. Telegram and application readback agree.
7. Replay creates zero additional rows, messages, actions or unrelated writes.

## Sequencing and handoff

1. Do not start while HERDMASTER's current deployment/verification mission or another serialized production owner is active.
2. Reconcile all terminal feedback and current production lineage first.
3. Repeat governance preflight in HERDMASTER's own clean worktree and read the authoritative standard completely.
4. Reconcile this plan with the current tracked breeding-attention workflow and production schema; do not blindly implement this local document if it is absent from authoritative lineage.
5. Implement and prove the application path first, then the shared Telegram journey, then one real supervised canary.

## Future continuation prompt seed

Address to: **HERDMASTER specialist terminal**, only after current terminal reconciliation and serialized-lane release.

> Governance preflight: verify the current clean worktree HEAD and confirm `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md` is Git-tracked; report its exact blob, SHA-256 and physical line count, then read it completely before acting. Read `docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_AND_UNKNOWN_PARENT_PLAN_20260812.md` and the current tracked HERDMASTER breeding-attention workflow completely. Reconcile both against current production lineage and schema. Deliver the approved owner-visible outcome: keep 17-day boar exposure separate from exact service/conception; create an explicit body-condition recovery hold that excludes a sow from recommendations until fresh evidence and governed clearance; preserve near-farrowing and litter truth when historical mating date and father are Unknown; refresh the practical breeding worklist from those facts; and prove the same concise grouped journey through the application and authenticated Oom Sakkie path. Preserve history, do not invent dates, fathers, pregnancy or service, do not create a competing ledger, and remain outcome-bound until a fresh genuine end-to-end canary and canonical readback succeed with zero-row replay and zero unrelated writes.

