# HERDMASTER Weaning-led Mating Recovery Plan

Status: owner-approved doctrine and implementation recovery plan.

## Owner-visible outcome

After a litter is governed as weaned, HERDMASTER must place the female into an evidence-backed boar allocation sequence without asking Charl to observe standing heat first. The worklist must show who is due, the selected primary and reserve boar, intended placement/exposure dates, genuine holds and the next factual action.

## Binding farm rule

- Weaning chronology starts the mating-placement clock.
- Heat is expected roughly four days after weaning, but observing it is not required before placement.
- The female stays with the selected boar for 17 days to cover the intended heat opportunities.
- She then moves to an appropriate resting/rebuilding location; no pen is a permanent eligibility rule.
- Heat/no-heat may be recorded when noticed, but cannot delay placement, suppress a recommendation or create a repeated owner question.
- The exposure window is not proof of one exact service date. Preserve the interval unless an attributable service date is recorded.

## Genuine blockers that remain

- active pregnancy or conflicting reproductive-cycle evidence;
- an active/unweaned litter or nursing state;
- current welfare, medical, withdrawal or explicit owner hold;
- conflicting identity or a known unsafe family relationship;
- a current physical concern that makes placement unsafe.

Pen location, missing heat observation and low boar workload are not mating-readiness or genetic-quality reasons.

## Required implementation recovery

1. Remove observed/standing heat from readiness prerequisites in `herdmaster_breeding_attention_service.py`, `herdmaster_breeding_operating_loop.py` and `herdmaster_breeding_recommendation.py`.
2. Derive placement due/overdue status from canonical weaning and active reproductive lifecycle evidence.
3. Preserve pair ranking from production, survival, growth, maternal, repeat-pair, diversity, controlled-trial and known-relatedness evidence.
4. Model planned exposure, actual placement and attributable service evidence distinctly; never invent a mating or exact service date.
5. Rebuild the current worklist so females incorrectly held for missing heat evidence are reassessed immediately.
6. Make Breeding Attention show the latest individual observation, time, resulting state, primary/reserve boar and next action instead of generic repeated text.
7. Retain heat fields only as optional historical-compatible observations and label them non-blocking.

## Completion proof

A fresh real-world journey for at least one governed weaned female must prove that canonical weaning is read, no heat observation is requested, an evidence-backed pairing is shown, genuine holds still work, the UI visibly reflects animal-specific evidence, no service date or farm effect is invented, and replay produces no duplicate effect. CI, deployment or a handover alone is not completion.

## Governance handoff

Before acting, the HERDMASTER terminal must verify and fully read the tracked Agentic Operating Mission Standard in its own clean current-main worktree and report its HEAD plus exact standard blob/SHA-256. It must then read this plan, `OWNER_DECISIONS.md`, the genetic-selection rules, practical mating plan, breeding-attention workflow and implementation source map. This later owner decision controls any conflict.
