# HERDMASTER Evidence Composition Source Handover

Status: source-only, not registered, not merged, not deployed

## Family outcome

An authenticated family member can ask one ordinary question about one exact
pig and receive one concise, sourced answer covering the requested supported
evidence plus missing/stale evidence and one useful next action. The contract
does not send the family to a form, page, sheet, or dashboard.

## Source contract

- Pure composer:
  `modules/oom_sakkie/herd_evidence_composition.py`
- Focused acceptance tests:
  `tests/test_herdmaster_evidence_composition.py`
- Supported question categories:
  - historical weight chronology;
  - current pen and movement summary;
  - on-farm presence, availability and purpose;
  - mating and litter chronology;
  - medical and withdrawal summary;
  - missing/stale evidence and one next action.

The contract accepts already-read canonical projections. It performs no
database, filesystem, network, registry, routing, Telegram, Render, n8n,
GateKeeper, writer, or protected-action operation.

## Governed boundaries

- Owner authentication is required before identity or herd evidence.
- One exact canonical animal is required. Ambiguity returns only a count and
  asks for the Pig ID; it does not list herd records.
- Weight, movement and medical rows require the exact subject Pig ID.
- Future or malformed dated evidence is excluded and disclosed as unusable.
- Pregnancy evidence is resolved only from rows where the subject is the
  canonical sow. A boar or female counterpart cannot inherit another sow's
  pregnancy result.
- Availability and purpose are state facts, not breeding, health, withdrawal
  or fertility clearance.
- Medical history never establishes medical or withdrawal clearance.
- Protected mating, medical, lifecycle, movement and availability actions
  remain separate and require their governed workflow and owner authority.
- Missing evidence blocks only its unsupported claim; other supported facts
  remain visible.
- Output is deterministic, privacy-bounded, read-only and zero-write.

## Deferred Oom Sakkie integration

Do not perform these edits until Control Tower explicitly assigns HERDMASTER a
serialized integration window:

1. `modules/oom_sakkie/tools.py`
   - add one authenticated read-only tool wrapper;
   - use existing canonical read services:
     `get_weight_history_for_pig`, `get_movement_history_for_pig`,
     `get_treatment_history_for_pig`, `get_mating_overview`, and
     `list_litter_overview`;
   - supply the current canonical animal state and existing governed
     HERDMASTER recommendation;
   - pass only exact-subject projections to the pure composer.
2. `modules/oom_sakkie/service.py`
   - add bounded deterministic intent selection for the supported evidence
     questions;
   - do not route write requests or unsupported medical/lifecycle claims into
     this read-only contract.
3. Shared registration/tests
   - prove authenticated owner access, ordinary Oom Sakkie and specialist
     route health, privacy-safe ambiguity, and zero writes;
   - preserve exactly one Telegram trigger and every unrelated specialist
     route and configuration.

No new writer, page, form, dashboard, table or duplicate litter/lifecycle/
medical workflow is required.

## Future operational proof

After normal merge, exact-merge CI and exact deployment, send one fresh
authenticated read-only question such as:

> What do you know about Shupe's weights, movements, mating and litter
> history, medical and withdrawal evidence, and what should we do next?

Require one answer containing exact identity, dated canonical chronology,
provenance, scoped Unknown/stale evidence, the governed HERDMASTER
recommendation and one next action. Compare farm table counts before/after and
prove zero farm writes, zero protected actions and no unrelated animal
context. Do not replay historical Telegram executions.

