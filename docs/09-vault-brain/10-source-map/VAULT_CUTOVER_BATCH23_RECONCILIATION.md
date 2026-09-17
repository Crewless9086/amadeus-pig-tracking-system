# Vault Cutover Batch 23 Reconciliation

Status: `COMPLETE / THIRTEEN ROOTLINE SOURCES ARCHIVED / CURRENT CONTRACTS RETAINED`
Date: 2026-08-18
Baseline: `73f1638fbea49e53fb8f3c983bf671742a13e450`

## Scope And Result

Thirteen ROOTLINE plans, inventories, canaries, onboarding notes, contracts and
commissioning packets were read and reconciled. Their durable planning,
device-class, authority, execution, fail-OFF, provider/physical verification
and owner-visibility rules now live in focused Vault authority. Originals are
preserved intact under `docs/99-archive/vault-cutover/docs/06-operations/` and
cannot steer new work.

## Current Authority Retained

- `02-agents/farm/ROOTLINE.md` owns ROOTLINE role and operating behavior.
- `04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md` owns staged authority,
  deterministic execution and independent device-class graduation.
- `08-business-rules/ROOTLINE_WATER_ENERGY_RULES.md` owns water, irrigation,
  fertiliser, borehole, evidence and standing-envelope policy.
- Current operational state requires the Control Tower mission register plus
  fresh canonical, provider and physical evidence.

## Boundaries

- No document was deleted; all thirteen were archived intact.
- No runtime, message, provider, database, farm, irrigation, fertiliser,
  borehole or other hardware effect occurred.
- The remaining physical queue is 57 documents in Batches 24 through 27.
