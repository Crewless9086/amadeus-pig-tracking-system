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

Phase 2 implementation uses the existing canonical
`pig_observation_events` rail without a new migration. Owner-read may inspect
history; only an authenticated owner-admin principal may append evidence.
Preview separates observed facts, owner interpretation and the resulting
Herdmaster explanation. Replay is withheld, altered evidence under the same
identity conflicts, and corrections append a same-animal superseding event.
No observation is itself a heat, pregnancy, fertility, health, breeding
readiness, retirement or mating decision.

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

The current foundation breeding population follows Charl's bounded unrelated-owner baseline in `docs/09-vault-brain/08-business-rules/HERDMASTER_GENETIC_SELECTION_RULES.md`. Rank exact combination merit before applying physical capacity. Do not equate low service workload with genetic superiority. Classify each choice as Proven repeat, Supported cross, Corrective cross, Controlled trial, or Limited evidence. Prince and every future new boar must receive a purposeful bounded trial rather than automatic preference or blanket exclusion.

After individual pair assessment, create one whole-round allocation grouped by boar. The normal initial physical limit is two or three females per immediate boar group, but equal distribution is not required and capacity may not override known relationship or production evidence. Females outside the immediate group remain sequenced and visible until an attributable mating or genuine hold is recorded.

## Agentic operating loop — primary owner workflow

OOM SAKKIE is the primary owner interface for ordinary breeding work.
Breeding Attention is the matching evidence, audit and recovery surface; it is
not a separate workflow Charl must manually operate.

Each Monday, HERDMASTER reconciles current canonical evidence and presents only
females requiring attention. It groups physical work, asks only for facts not
already answered by fresh immutable evidence, reassesses readiness, and
prepares a fail-closed male recommendation and plan-only owner decision packet.
Current agentic functions include:

- Monday actionable breeding worklist;
- overdue pregnancy checks;
- eligible but unmated females;
- expected farrowings;
- missing physical observations;
- repeat-service, replacement, or retirement review;
- owner decisions waiting.

Observation recording, mating execution and reminder delivery remain separate
governed actions. The deployed OOM exchange previews directly stated physical
facts but does not yet append them. A mating may be created only after one
exact owner approval bound to the female, male, evidence generation and mating
date. CORE may later provide scheduling and delivery, but is not the owner of
breeding reasoning and is not a prerequisite for the HERDMASTER workflow.

The ordinary Oom Sakkie journey must reuse the append-only observation rail for
grouped natural reports while binding every fact to its exact female and
observation time. The Breeding Attention/mating board remains the owner recovery
surface. Do not create a second observation store or require Charl to repeat a
fact already captured through either governed entry point.

## Authority and safety

Herdmaster remains advisory. No observation or recommendation may automatically:

- create or change a mating;
- assert pregnancy or heat;
- change medical, lifecycle, purpose, movement, availability, reservation, sale, or retirement state;
- notify a customer or make a commercial promise;
- schedule recurring work or grant CORE execution authority.

Actual farm-record changes require a separately reviewed backend action and explicit owner approval.

## Exposure, recovery hold, and unknown-parent boundary

Physical boar exposure is not an exact service, mating, conception, or
pregnancy date. HERDMASTER records an actual exposure start and later removal
as separate immutable events under one exposure identity; the planned removal
date belongs to the start event. These events must never populate
`mating_events.mating_date` or generate pregnancy/farrowing dates.

Body-condition and near-farrowing facts continue to use the canonical
append-only `pig_observation_events` rail. A BCS 2-or-lower observation may be
bound to an explicit recovery hold. Clearance requires a fresh attributable
BCS 3-or-higher observation plus a separate exact owner confirmation; elapsed
time and a newer score alone never clear a hold. A current near-farrowing
observation excludes the sow from placement without manufacturing a father or
historical mating date.

The existing litter workflow accepts a canonical mother with `boar_pig_id`
and historical `mating_id` absent. Unknown parentage remains visible as
Unknown and does not degrade or duplicate the litter.

## Delivery order and acceptance

1. Finish and verify the current one-animal Auction List Add canary.
2. Reconcile current production breeding evidence and stale historical mission/PR lineage.
3. Build and visually prove the integrated Breeding Attention and observation workflow.
4. Independently review, merge, deploy, and perform read-only live verification.
5. Run one supervised sow observation canary without creating a mating.
6. Verify the observation changes Herdmaster's explanation while leaving farm records unchanged.
7. Prepare one separately authorized mating-record canary only after the recommendation and owner decision are proven.
8. Add recurring delivery only after the OOM-first workflow is operational and
   deduplication/no-spam evidence is proven.

The first operational acceptance requires a real owner-recorded observation, an explained updated recommendation, zero unintended farm mutations, and a clear worklist Charl and his father can use without reading technical evidence.

## Phase 1 operational result - 2026-07-27

Phase 1 was merged through PR #549 as
`028b4181c1c5cd22ffeef5824b7ec9a475458d29` and deployed by Render as
`dep-d9jqt0ok1i2s73c4gshg` at that exact revision. All exact-merge checks
passed and `/health` returned HTTP 200.

The deployed owner-authenticated, GET-only proof completed in 3.828 seconds:

- authoritative current sow/gilt inventory: 18, complete;
- Pregnancy evidence: 9;
- Post-litter recovery: 3;
- Needs Data: 6;
- Hold, Needs observation, Ready for review and Recently mated: 0;
- counts reconciled exactly to all 18 animals;
- supporting evidence status: partial;
- family expansion: partial for all 18 within one bounded in-memory expansion;
- writes and protected actions: none.

The partial evidence result is intentional and fail-closed. At this evidence
cut all 18 females lacked affirmative availability, current body-condition,
current heat-observation, complete family-tree and withdrawal evidence. These
facts remain missing; they are not inferred as safe, ready, unsuitable,
not-pregnant or zero.

Phase 1 is operational as an owner-only read surface. The next phase is a
separately reviewed, append-only human-observation workflow. Its first canary
should record one factual sow observation, then verify read-only that the
explanation changes while mating, pregnancy, medical, lifecycle, purpose,
movement, availability, retirement, customer, notification and farm state
remain unchanged.

## OOM SAKKIE Monday loop operational result — 2026-07-28

The proactive worklist was introduced by PR #581 and its independent-review
correction was integrated by PR #582 as
`bc035f304f4ffd10e08dd8222216baa0c5347e84`. Render deployment
`dep-d9kf41hsrm7s73883kl0` serves that exact revision and `/health` returned
HTTP 200. Exact-merge CHARLIE CORE, disposable-PostgreSQL audit rails and
Playwright gates passed.

The single owner-authenticated, GET-only operational proof completed in 3.89
seconds:

- authoritative current sow/gilt inventory: 18, complete;
- actionable Monday tasks: 7;
- pregnancy checks due: Baby, Mona and Mysikind;
- post-litter recovery checks: Teena and Waki;
- weight/readiness checks: Linda and Ms Piggy;
- supporting evidence status: partial;
- counts reconciled to the complete inventory;
- observation recording, mating execution and reminder delivery: disabled;
- writes and protected actions: none.

Baby is the first actionable current candidate because a canonical mating is
70 days old and governed pregnancy evidence is due. This is a request for a
truthful physical/governed pregnancy check, not an assertion that she is
pregnant or not pregnant.

The current safety correction requires fresh canonical observation projections
(48 hours for heat; 30 days for body condition and physical facts), complete
bounded family expansion for both female and male, and stable exact-evidence
task/approval identities. Incomplete, cyclic, ancestor/descendant or
shared-ancestor evidence fails closed. Protected animal worklist tools are
deterministic-only and never send raw exact-animal context to an external
answer composer.

The next supervised operating proof may collect one truthful factual inspection
through an exact owner-approved append-only action, then reassess the same
task. It must not create a mating, reminder or farm-state change. A later
separate approval is required for an exact female/male mating packet.
