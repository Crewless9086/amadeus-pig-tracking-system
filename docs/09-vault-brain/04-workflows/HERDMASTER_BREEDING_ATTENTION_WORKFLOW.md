# Herdmaster Breeding Attention and Human Observation Workflow

Status: owner-approved direction, queued after the supervised Auction List first-use canary reaches a clean verified stopping point.

This workflow is separate from the Riversdale Auction workflow. An auction-quality observation may remain useful factual evidence, but auction review, Auction List membership, breeding suitability, mating recommendations, and mating records are different decisions and must never imply one another.

## Business outcome

Charl and his father need one owner-only Breeding Attention view that identifies every current sow or gilt, explains her reproductive state, shows decisive missing evidence, and recommends the next human action. Herdmaster should help prevent eligible females from standing idle and should carry human knowledge about body, build, temperament, maternal performance, reproductive signs, and breeding preferences into later recommendations.

The initial useful outcome is an explained daily worklist, not autonomous mating.

## Existing foundation

- Canonical Supabase pig, mating, litter, family-tree, weight, medical, movement, pen, and purpose evidence.
- Existing mating board and breeding analytics.
- Merged read-only Herdmaster breeding planner from PR #414.
- Append-only `pig_observation_events` evidence rail now used by the bounded Auction review workflow.
- Historical CORE missions:
  - `CHARLIE-HERDMASTER-OBSERVATION-INTENT-INTEGRATION-20260721-R63C034E2`
  - `CHARLIE-HERDMASTER-BREEDING-PLANNER-20260721-RI748BC303`

The historical observation/management-intent candidates are not merge instructions. They must be reconciled against current main; stale or overlapping PRs must not be revived.

## Current boundary

The breeding planner can calculate advisory mating/calendar states, but current canonical evidence is incomplete for safe matching. Human conformation and management observations do not yet flow through a general breeding capture surface. The Auction review surface is narrower and must not be treated as the general breeding workflow.

Live evidence reviewed on 2026-07-27 showed 19 sows with breeding history, 3 boars, and 15 mating records. Five sows appeared with no mating record in the analytics and seven had an open mating record. Those counts are attention signals only: absence of a mating does not prove readiness, and an open record does not prove current pregnancy.

## Phase 1 - Breeding Attention view

Produce one owner-only table with one current explained state per sow or gilt:

- ready for mating review;
- standing or heat observation required;
- recently mated;
- pregnancy check due or overdue;
- expected to farrow;
- nursing or post-weaning recovery;
- owner hold;
- retire or replace review;
- needs data or conflicting evidence.

Every row must show the evidence date, reason, missing facts, confidence, and one recommended next human action. Missing evidence must display as `Needs Data`, never as ready, not pregnant, healthy, or unsuitable.

## Owner-confirmed reproductive operating model

Routine Amadeus Farm breeding management uses scheduled mating, calculated dates, visual inspection, and continued observation. Routine visual inspection is not a clinical pregnancy diagnosis.

The managed cycle is:

1. **Mating scheduled/completed:** deliberate placement with the selected boar and an exact mating record start the cycle.
2. **Post-mating quiet phase:** the farm provisionally works on the assumption that mating may have taken, while biological pregnancy remains unconfirmed.
3. **Pre-farrowing visual reassessment:** roughly one month before the calculated due date, or at the next practical inspection, assess visible signs such as belly development/dropping and udder or milk development.
4. **Assumed Pregnant:** supported visual signs justify this farm-management status and movement to the farrowing pens. It is not a scan-confirmed or clinical diagnosis.
5. **Pregnancy Uncertain / Does Not Appear Pregnant:** insufficient or contrary visual signs require reassessment; they do not prove `Not Pregnant`.
6. **Farrowing watch:** around and after the calculated due window, observe until farrowing or enough later evidence supports an owner-approved cycle outcome.
7. **Observed farrowing or governed outcome:** only an actual litter/farrowing record or stronger attributable evidence closes the cycle.

HERDMASTER must keep recorded mating, provisional post-mating planning, visually `Assumed Pregnant`, clinically governed pregnancy evidence, movement to a farrowing pen, and actual farrowing as separate facts. Passing an expected date without farrowing triggers reassessment; it does not automatically prove an empty sow. Until the farm confirms its preferred term for a cycle producing no litter, use `missed-cycle review` rather than inventing or normalizing `skip`.

### Natural grouped or individual observations

Charl may report one sow, several sows, or the whole group across one or several natural messages. Oom Sakkie and HERDMASTER must accumulate partial answers without asking again for supplied facts.

- `Baby does not look pregnant to me.` means visual inspection and `Pregnancy Uncertain / Does Not Appear Pregnant`, with reassessment.
- `Mona and Mysikind look pregnant; their bellies are dropping and they are producing milk.` produces two separate `Assumed Pregnant` previews supported by those visible signs.

For an authenticated owner message, use its provider timestamp as the observation time and authenticated sender as assessor by default. Ask for another time only when the observation happened earlier or timing is materially ambiguous. Natural visible-sign wording is sufficient to classify the method as `visual inspection`; do not demand form-like repetition.

Every fact still requires an exact per-sow preview bound to the current mating cycle and explicit confirmation before a governed write. Grouped input may produce grouped previews, but confirmation and replay protection remain exact per sow/cycle fact.

## Phase 2 - General human observation capture

Add an owner-only, append-only factual observation workflow for:

- body condition;
- conformation and body build;
- legs and feet;
- udder and teats;
- temperament;
- mothering performance;
- reproductive or standing signs;
- defects or concerns;
- owner breeding preference.

Each observation must bind the canonical `Pig_ID`, observation time, recording time, server-derived owner identity, factual note, controlled category, optional measurements, confidence/provenance, and optional canonical media reference.

Observation receipt is not a management decision. A comment must not silently change pregnancy, mating, medical, purpose, lifecycle, availability, retirement, or sale state.

## Phase 3 - Explained mating recommendations

Herdmaster may rank evidence-qualified pairings using:

- current reproductive state and recovery period;
- mating, pregnancy, farrowing, litter, and weaning history;
- human observations and owner preferences;
- body condition and known conformation strengths or concerns;
- sow and boar family trees and relatedness exclusions;
- litter performance and repeat-service history;
- medical, withdrawal, movement, reservation, purpose, pen, and availability evidence;
- farm capacity and timing.

Each recommendation must name supporting evidence, exclusions, uncertainty, and the owner decision required. Herdmaster must not infer heat, pregnancy, fertility, soundness, genetics, or physical suitability from missing evidence.

## Phase 4 - Agentic operating loop

After the owner workflow is proven, CORE may schedule read-only Herdmaster observation and escalation:

- daily breeding-attention digest;
- overdue pregnancy checks;
- eligible but unmated females;
- expected farrowings;
- missing physical observations;
- repeat-service, replacement, or retirement review;
- owner decisions waiting.

CORE is not a prerequisite for Phases 1-3. CORE later provides continuous observation and delivery; it does not replace the Herdmaster business capability.

## Authority and safety

Herdmaster remains advisory. No observation or recommendation may automatically:

- create or change a mating;
- assert pregnancy or heat;
- upgrade `Assumed Pregnant` into clinically confirmed pregnancy;
- change medical, lifecycle, purpose, movement, availability, reservation, sale, or retirement state;
- notify a customer or make a commercial promise;
- schedule recurring work or grant CORE execution authority.

Actual farm-record changes require a separately reviewed backend action and explicit owner approval.

## Delivery order and acceptance

1. Finish and verify the current one-animal Auction List Add canary.
2. Reconcile current production breeding evidence and stale historical mission/PR lineage.
3. Build and visually prove the integrated Breeding Attention and observation workflow.
4. Independently review, merge, deploy, and perform read-only live verification.
5. Run one supervised sow observation canary without creating a mating.
6. Verify the observation changes Herdmaster's explanation while leaving farm records unchanged.
7. Prepare one separately authorized mating-record canary only after the recommendation and owner decision are proven.
8. Add recurring CORE observation only after the owner workflow is operational.

The first operational acceptance requires a real owner-recorded observation, an explained updated recommendation, zero unintended farm mutations, and a clear worklist Charl and his father can use without reading technical evidence.
