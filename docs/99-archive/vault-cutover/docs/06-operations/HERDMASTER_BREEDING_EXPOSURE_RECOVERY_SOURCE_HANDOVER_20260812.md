# HERDMASTER breeding exposure and recovery source handover — 2026-08-12

Status: Prepared; not merged, deployed, operational, or Business-complete.

## Governance and lineage

- Worktree: `C:\tmp\herdmaster-breeding-exposure-recovery-20260812`
- Branch: `feat/herdmaster-breeding-exposure-recovery-20260812`
- Base: `3aac7061c408cdec9bbdbc26390775cc2eaa4533` / `origin/main`
- Mission Standard blob: `a2e17a434a5ca0449905e40aeb1a7fa07bd6268e`; 603 checked-out physical lines read completely.
- Approved plan blob: `272a71c11b4a89c3c610cfdf23f0467359104856`; read completely.

## Challenge result

`mating_events.exposure_group` is not a safe exposure rail because the current
writer requires `mating_date` and derives pregnancy-check and farrowing dates.
No production exposure table exists. The smallest safe model addition is one
append-only exposure-event table with immutable `started` and `removed`
events. Recovery and near-farrowing facts reuse `pig_observation_events`;
unknown-father litters reuse the existing litter writer.

The bounded production read found no mating rows for Linda or Ms Piggy and no
canonical exposure rows, so no proposed placement may be treated as actual.
Linda's existing litter history already contains `boar_pig_id=NULL`. Ms Piggy
has a BCS 2 owner observation on 2026-07-28 and a newer BCS 3 observation on
2026-08-11. Both remain immutable; the owner-directed recovery hold remains
active until a fresh attributable score and explicit governed clearance are
recorded. A newer score or elapsed time does not auto-clear it.

## Prepared contract

- One grouped preview requires every supplied sow exactly once and rejects the
  complete operation if any row is malformed, duplicated, or unsupported.
- Supported actions: exposure start, exposure removal, recovery hold,
  recovery clearance, and near-farrowing observation.
- Exposure start retains sow, boar, actual start, planned removal, source and
  deterministic identity. Removal is a second immutable event.
- Hold requires BCS <=2. Clearance requires a fresh explicit BCS >=3 plus the
  exact protected confirmation. Near-farrowing retains father and historical
  mating date as Unknown.
- Application routes use strict owner-admin identity and exact preview hash.
- The operating loop consumes the append-only exposure projection. It excludes
  active exposures, active recovery holds, and near-farrowing sows while
  retaining history and no mating authority. A removal closes only its exact
  exposure identity and never manufactures a service date.
- Existing litter validation accepts mother with father/mating absent.

## Existing Oom Sakkie boundary

The typed adapter is
`modules/oom_sakkie/herdmaster_breeding_exposure_runtime.py`. It accepts only
already-authenticated, already-resolved canonical rows and reuses
`app_private.oom_protected_action_claims`, the existing callback buttons, and
the existing protected callback precedence in
`modules/oom_sakkie/protected_action_runtime.py`. The shared gateway addition
is limited to dispatching that typed packet after semantic interpretation.
There is no second router, Telegram sender, claim store, or persistence path.

The existing semantic front door now emits a bounded `breeding_actions` list
containing owner-stated references and facts only. The adapter resolves every
sow and boar against the current canonical breeding snapshot and derives the
evidence generation server-side. Ambiguous or partly resolved groups are
rejected with one grouped question before claim creation. Confirmation
executes the exact stored preview and completes or contains the existing
claim. No source path sends Telegram by itself.

## Verification

- Focused application, projection, read-service, semantic-front-door, Oom
  Sakkie claim and gateway tests: 152 passed.
- Python syntax parsed successfully for every affected module.
- `git diff --check`: clean.
- Read-only production reconciliation performed zero writes.

## Current real facts and required future group

- Ms Piggy / `PIG-2026-92F3`: recovery hold required; preserve both BCS events.
- Linda / `PIG-2026-5AA8`: near-farrowing observation required; father and
  historical mating date Unknown.
- Actual physical sow-boar placements remain Unknown. If canonical evidence
  remains absent after deployment, ask one grouped question containing only
  the sow-boar pairs and common actual placement date still needed.

## Serialized integration and genuine acceptance

Do not acquire runtime while ROOTLINE or an existing Oom Sakkie genuine-event
lifecycle owns it. After explicit release: reconcile current main; run exact
head reviews/CI; merge normally; run exact-merge CI; deploy exact lineage;
apply only the reviewed migration; verify health and owner routes. Use the
prepared existing-rail Oom Sakkie protected-action action kind; do not add a
router or Telegram lifecycle. One authenticated grouped message must produce
one preview, one protected confirmation, one atomic operation, application and
Telegram readback agreement, refreshed Breeding Attention, and zero-effect
replay. A genuine later farrowing must prove the existing litter writer accepts
father/mating Unknown. Release runtime whenever waiting for physical facts.

Business completion requires fresh real exposures, visible hold and explicit
clearance, unknown-parent litter acceptance, refreshed recommendations, and
provider-confirmed replay/zero-unrelated-write proof. Source/CI/deployment are
not completion.
