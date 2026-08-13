# Matings Active Exposure UI Simplification Plan

## Status

Owner-approved coordinated read-model and UI mission. The five 12 August active cycles exist in canonical production; backend projection correction and UI implementation have not started.

## Production evidence that triggered this extension

The live `/api/pig-weights/matings` response on 2026-08-12 contained exactly five new `Exposure Active` cycle rows for Sophie/Bola, Olive/Tyson, Shupe/Tyson, Lucy/Tyson and Lolly/Prince. Their canonical IDs, current pens, `IN`, planned `UIT`, possible-service window and expected-farrowing window were present. Their projected `sow_tag_number` and `boar_tag_number` values were blank.

The current card renderer falls back from those blank names to canonical Pig IDs and still prioritises the legacy single `mating_date`, `Open` status and one `expected_farrowing_date`. This makes correct window-based records look incomplete or incorrect. The underlying pairing facts must not be rewritten merely to compensate for a read-model or presentation defect.

The live Breeding Attention/operating-loop presentation also continued to place already-exposed females in `Plaas Nou`. Its scheduler anchors an immediate cohort to Wednesday of the current work week, which was 2026-08-12, but active exposure evidence must exclude those females before cohort scheduling. They belong in a separate current-state group, not `Plaas Nou` or `Volgende Groep`.

Molly's newly confirmed 2026-08-11 litter exposed a second lifecycle-precedence defect. Breeding Attention can select retained pregnancy evidence before evaluating the newer attributable farrowing/litter outcome. Historical pregnancy evidence must remain preserved, but it must not continue to describe the sow's current state after confirmed farrowing.

Bonnie, Waki, Zigay and Teena exposed a third eligibility defect. Their latest governed 2026-08-11 body-condition observations are below the farm's approved mating threshold, yet the operating loop still placed them into a breeding cohort. The loop currently loads a fresh `body_condition_score` but does not apply it when deriving `Ready for mating review`; a governed weaning date can therefore override poor recovery condition. This is unsafe and operationally incorrect.

## Coordinated ownership

This mission has two ordered slices:

1. **HERDMASTER read-model correction:** correct and verify the canonical `/matings` projection contract for window-based natural exposure cycles.
2. **Codex/UI implementation:** consume the corrected contract and complete the compact active-exposure and individual-card presentation.

HERDMASTER must not redesign the page. Codex/UI must not infer animal identity or breeding semantics that the authoritative read model does not supply.

## HERDMASTER read-model contract

The `/api/pig-weights/matings` projection must:

1. Resolve owner-facing sow and boar names from authoritative canonical animal state when the immutable cycle row does not retain a display name.
2. Use historical event display text only as a secondary fallback, and use canonical Pig ID only when no authoritative human-readable identity exists.
3. Surface both names and IDs as separate fields; never place an ID into a name field.
4. Reconcile the current authoritative animal name for `PIG-2026-069E` rather than silently choosing between historical `Olivia` and owner-reported `Olive`.
5. Expose a typed cycle presentation state for natural exposure, including owner-facing meaning equivalent to `By beer`, rather than requiring the browser to derive it from `Open`.
6. Treat `service_window_start`, `service_window_end`, `exposure_planned_removal_on`, `exposure_actual_removal_on`, `expected_farrowing_window_start` and `expected_farrowing_window_end` as first-class cycle facts.
7. Keep `mating_date`, exact service, conception and pregnancy empty or Unknown when they are not proven.
8. Expose the next action and its timing from canonical evidence: planned removal upcoming, due or overdue; no action may imply that planned removal actually occurred.
9. Preserve old exact-date mating records without forcing them into the window-based shape.
10. Add regression coverage for blank event display names, canonical-name enrichment, historical-name conflict, window-based cycles, exact-date legacy records and unchanged canonical facts.

### Current lifecycle precedence

Current-state projection must use the newest attributable lifecycle truth without deleting history. At minimum:

1. current medical, withdrawal or explicit owner hold;
2. active physical boar exposure;
3. confirmed farrowing with an unweaned litter: owner-facing `Soog tans`/post-litter state;
4. confirmed weaning: post-weaning recovery or readiness review;
5. currently attributable pregnancy evidence;
6. open or unresolved mating evidence; and
7. general breeding review.

A linked/attributable farrowing must supersede the prior pregnancy state in the current summary. An unweaned litter must not be presented as pregnancy, ready placement or generic unresolved evidence. Confirmed weaning must automatically move the derived state forward without a second manual lifecycle update.

Add a Molly-like regression journey (pregnancy evidence followed by a linked confirmed litter) and a Bella-like nursing comparison. Prove both current states are derived consistently while their distinct dates and history remain intact.

### Placement cohort exclusion

Before scheduling `Plaas Nou` or `Volgende Groep`, exclude every female with a canonical active exposure start that has no matching actual removal. This exclusion must be identity- and chronology-bound, not based on the calendar date alone.

Active exposure females must appear exactly once under a separate owner-facing current group such as `Tans by beer`, with:

- sow and boar names;
- actual `IN`;
- planned `UIT`;
- current pen; and
- no new placement recommendation.

They must appear in neither `Plaas Nou` nor `Volgende Groep`. After genuine actual `UIT`, the next derived state must follow the canonical removal/cycle rules; the scheduler must not immediately manufacture another placement.

The Wednesday/week-start anchor may remain for truly unplaced eligible cohorts, but `today` must never override completed placement evidence. Add regression coverage for a plan generated on the same day as placement, later within the exposure window, and after actual removal.

### Body-condition readiness gate

Before a female can enter `Plaas Nou` or `Volgende Groep`, the operating loop must evaluate the latest valid, non-superseded and sufficiently fresh body-condition observation against the authoritative farm breeding threshold.

Required behaviour:

1. A fresh score below the approved minimum is a current recovery hold and blocks physical placement.
2. A fresh score above any approved maximum also blocks placement pending owner/welfare review.
3. Time since weaning, a prior recommendation, available pen capacity or today's schedule date must never override an out-of-range score.
4. The sow appears exactly once under an owner-facing recovery/hold group with her current score, observation date, threshold meaning and next useful action.
5. The system must not invent a target date for recovery or automatically clear the hold as time passes.
6. Clearance requires a later governed, attributable body-condition observation inside the approved range, plus any other applicable welfare/availability gates. The later evidence supersedes the current decision without deleting history.
7. If the score is missing or stale, show `Needs current condition` rather than treating the sow as ready or assuming a low score.
8. The authoritative threshold must come from the shared breeding policy used by recommendation logic; do not copy a second hard-coded threshold into the UI or operating loop.
9. Owner-facing text must explain the operational fact concisely, for example `Herstel — kondisie 2; nog nie gereed vir beerplasing nie`.
10. Do not treat body condition as genetic merit, fertility proof, pregnancy evidence or a permanent do-not-breed decision.

Add real regression cases for Bonnie, Waki, Zigay and Teena using their latest 2026-08-11 governed observations. Before integration, reconcile the exact stored scores and evidence identities from production; do not rely only on this plan's summary. Prove all four are excluded from both placement cohorts whenever their fresh scores remain below threshold, and prove an in-range later observation can restore ordinary readiness review without automatically creating a placement.

The current five rows must remain exactly five. This read correction creates no exposure, movement, removal, service, conception, pregnancy, litter or other farm write.

## Owner-visible outcome

The `/matings` page must present natural boar exposure as ordinary farm work, not as a permanent technical governance panel.

When one or more exposure groups are active, Charl must be able to see at a glance:

- which boar is with which sow or sows;
- the actual `IN` date;
- the planned `UIT` date;
- whether removal is due, upcoming or overdue; and
- one plain-language action to record the genuine `UIT` date after physical separation.

When no active exposure group awaits removal, the entire exposure workspace must be absent. It must not leave an empty card, heading, placeholder or unexplained white space.

## Product-language correction

Do not use `BESKERMDE OORGANG` as the primary owner-facing label. That is an implementation and safety classification, not the farm job.

Use concise owner-facing Afrikaans such as:

- `Soe by beer` for the section heading; and
- `Teken werklike UIT aan` for the action.

The exact spelling and approved Afrikaans terminology must be checked with the existing UI language before owner review.

## Required interaction

1. Load active canonical natural-exposure groups.
2. If there are none, do not render the section.
3. If groups exist, render one compact task section above the general breeding register.
4. Group rows by boar and exposure group where that matches canonical evidence.
5. Prefer animal names. Keep canonical IDs secondary or inside expanded evidence only.
6. Show `IN`, planned `UIT` and a clear due/upcoming/overdue state.
7. Clicking `Teken werklike UIT aan` opens the actual-removal-date action for that exact group.
8. Only after the owner selects the action should the protected preview be shown.
9. Preserve exact preview binding, explicit confirmation, atomic grouped execution, replay protection and all existing fail-closed validation.
10. After successful execution, refresh both the active-exposure section and breeding register. Hide the section automatically when no active group remains.

## Individual cycle-card contract

Window-based exposure cards must show, at first glance:

- `Sog x Beer` using authoritative names;
- the current owner-facing state, such as `By beer`;
- `IN`;
- planned or actual `UIT` with an explicit label;
- expected farrowing as a range; and
- current breeding pen.

Exact service, conception and pregnancy Unknowns belong in secondary evidence. Internal `MAT-EXPOSURE-*` and `HERD-EXPOSURE-GROUP-*` identities belong in technical details, not the card heading.

Older exact-date mating records retain an appropriate exact-date presentation. Current exposure and historical cycles for the same sow are not duplicates; the current cycle must be visually primary and older completed history secondary.

## Non-goals and safety boundaries

This mission must not:

- change exposure, breeding-cycle, service, conception, pregnancy, movement or litter semantics;
- manufacture an actual `UIT` date from the planned date;
- record removal merely because the planned date arrives;
- remove the protected preview or confirmation boundary;
- create a second browser-only interpretation of the Telegram/voice workflow;
- change existing canonical records during visual preview or testing; or
- expose internal hashes, governance terminology or database identities as primary owner actions.

The planned `UIT` date remains a plan. The actual `UIT` date is recorded only after physical separation is reported and confirmed.

## UI requirements

Follow:

- `docs/09-vault-brain/07-standards/AMADEUS_FARM_UI_FACELIFT_STANDARD.md`;
- `docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md`; and
- the live dashboard plus approved descendant pages as the visual baseline.

The section must be compact, responsive and task-oriented. It must not dominate `Huidige teelwerk`, duplicate the breeding cards, create large empty areas or show technical protection language before an action is selected.

Required states:

- loaded with active groups;
- no active groups, with the section omitted;
- loading without layout jump where practical;
- read failure with one concise inline message;
- preview awaiting confirmation;
- successful grouped removal; and
- stale or conflicting preview requiring refresh without partial writes.

## Verification and owner acceptance

Build in an isolated clean worktree from authoritative main after current terminal work is reconciled. Preserve the existing uncommitted `/matings` facelift work until it is safely integrated or otherwise classified.

Acceptance requires:

1. A local desktop/laptop preview using a faithful active group.
2. Proof that the entire section is absent for an empty result.
3. Proof that group names, boar/sow assignments, `IN`, planned `UIT` and states are readable without opening technical details.
4. Proof that the protected preview appears only after the owner chooses the removal action.
5. Existing grouped-action and replay tests remain green.
6. No visual clipping, overflow or unnecessary white space.
7. Charl reviews and explicitly approves the local sample before deployment.
8. Business completion requires a later genuine physical separation journey to succeed end to end; a local preview, deployment or synthetic test is not that real-world completion.

## Ownership and sequencing

Primary owners: HERDMASTER for the read-model slice, followed by the Codex/UI workspace (or a specifically assigned CORE UI terminal) for presentation.

HERDMASTER owns canonical identity, cycle meaning and the protected exposure/removal rail. Codex/UI owns the page hierarchy and interaction. Neither may create a competing record or interpretation path.

Execute after the currently active terminal feedback and production lanes are reconciled. Do not start from the dirty shared workspace or overwrite the existing `/matings` facelift edits.
