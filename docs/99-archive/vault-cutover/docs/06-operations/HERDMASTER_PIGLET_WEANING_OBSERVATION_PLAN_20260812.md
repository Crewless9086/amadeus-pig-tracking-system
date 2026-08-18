# HERDMASTER Piglet Weaning Observation Mission

Status: owner-approved plan; implementation not started.

## Owner-visible business outcome

During Weaning Day, Charl or another authenticated farm owner can mark notable
piglets and record short factual observations without opening every individual
pig profile. Each saved observation is bound to the exact canonical pig, remains
visible on that pig's history, and becomes cited supporting evidence in later
HERDMASTER purpose and breeding-candidate review.

The workflow must be quick enough to copy observations made on the paper record
while tags and weights are being entered. Positive observations are first-class
evidence; the capture surface must not imply that observations are only for
death, illness or defects.

## Problem being corrected

The litter detail manual Section 5 is a pre-weaning death workflow. Its notes
describe a litter death event and do not provide a safe pig-specific positive
observation path. The Weaning Day table already has exact pig identities, tags,
sexes and weights, but it cannot currently capture observations such as good
build, strong legs, good growth, calm temperament or future breeding potential.

General litter notes, medical notes, death notes and free text on a purpose
decision are not substitutes. They have different business meanings and must
not become shadow observation stores.

## Mission ownership

Primary implementation terminal: Codex UI/application terminal.

Why: the first missing capability is application workflow, exact row binding,
protected backend validation, visual design and browser acceptance on the
existing litter page. This work should be developed in an isolated clean
worktree and shown locally to Charl before deployment.

Specialist consumer: HERDMASTER.

HERDMASTER owns how the resulting evidence is cited, freshness-scored and used
in later purpose, retention and breeding-candidate recommendations. It must not
build a competing form, observation table or write rail. HERDMASTER integration
starts only after the capture contract is available or may be prepared in the
same source mission when production ownership is serialized safely.

## Reuse boundary

Reuse the canonical append-only `pig_observation_events` contract and its
existing protected observation service. Do not introduce a second observation
table, overload `General_Notes`, or store the fact only inside a litter/weaning
transaction payload.

Each event must preserve:

- canonical `pig_id` and current visible tag/name;
- canonical `litter_id` as associated context;
- observation time and separate recording time;
- authenticated observer identity and source provenance;
- controlled factual category or categories;
- concise factual note;
- context `weaning`;
- optional owner flag for future review;
- stable idempotency identity and append-only correction lineage.

Unknown facts remain Unknown. An observation is evidence, not a diagnosis,
purpose assignment, genetic conclusion, breeding clearance or management
decision.

## Weaning Day user experience

Extend each exact piglet row with a compact observation control that preserves
the readable weaning table on desktop and print-oriented workflows:

- `Hou dop` checkbox;
- `Waarneming` short text field;
- optional quick factual traits such as `Goeie bou`, `Sterk bene`, `Goeie
  groei`, `Breë lyf`, `Goeie temperament`, `Potensiële teeldier` and `Ander`;
- a clear indication when an existing observation for that pig and date is
  already recorded.

The owner may enter no observation for ordinary piglets. Blank rows create no
observation. Selecting `Potensiële teeldier` records an owner review signal,
not a purpose change.

The Weaning Day preview must show observations beside the exact tag/name and
must distinguish the existing weaning effects from new observation effects.
The executed transaction must either commit the exact approved observation set
with the approved weaning transaction or fail without a partial ambiguous
result. If the existing rail cannot participate atomically, use an explicit
receipt-bound continuation whose partial state is visible and safely
recoverable; never claim both outcomes committed when only one did.

## Historical/backlog capture

Provide the same compact pig-specific observation capture after weaning for
paper notes entered later. The owner selects the genuine observation date and
the exact piglets from one litter. It must not require re-running Weaning Day or
re-recording weights, treatments, tags, movements or litter completion.

This backlog path is required for the observations Charl and his mother made
during the 11 August 2026 weanings.

## HERDMASTER use

HERDMASTER may consume the observation only as attributable, dated human
evidence. Later review should combine it with:

- parentage and exact litter performance;
- born-alive and survival/weaning outcomes;
- weaning weight and later comparable growth;
- medical, welfare and mortality history;
- subsequent structural observations;
- later sale, slaughter, retention or breeding outcomes.

Every recommendation must cite the observation and its date, state its
freshness and limitations, and preserve contradictory or superseding evidence.
A favourable weaning observation should place the pig in a future review/watch
set; it must not automatically classify the pig as Retain/Breeding Candidate.
The existing 14-day post-weaning purpose-review timing remains unchanged.

## Safety and authority

- Owner-authenticated capture only.
- Exact canonical pig and litter membership must be revalidated at execution.
- No observation may create or change purpose, mating, pregnancy, medical,
  lifecycle, movement, availability, reservation, sale or slaughter state.
- No customer or Telegram message is generated by recording the observation.
- Replay creates zero additional events.
- Corrections append a same-pig superseding observation; no update or delete.
- Section 5 remains explicitly labelled and constrained as piglet death capture.

## Acceptance journey

1. Governance preflight passes in the implementing worktree and the current
   litter/weaning and observation contracts are reconciled completely.
2. Charl reviews and approves the local litter-page design using real-shaped
   piglet rows.
3. Exact backend preview proves row-to-pig binding and shows zero unintended
   weaning, medical, movement, purpose or lifecycle effects.
4. Source review, CI and browser behavior gates pass; deploy exact lineage.
5. Charl records one genuine historical or current positive observation for an
   exact tagged piglet.
6. Production readback shows exactly one append-only observation on that pig,
   visible from both the litter workflow and individual pig history.
7. HERDMASTER produces one refreshed, concise purpose-review explanation that
   cites the observation without changing the pig's purpose.
8. Exact replay creates zero additional observations or other farm effects.

CI, deployment and a synthetic event are not Business completion. Completion
requires the genuine owner journey through capture, readback and HERDMASTER
consumption.

## Explicit exclusions

- Redesigning the whole litter page.
- Rewriting the paper form.
- Automatic breeding retention or purpose assignment.
- Using Section 5 or death notes for positive observations.
- Replacing the general Breeding Attention workflow.
- Creating a second observation ledger.
