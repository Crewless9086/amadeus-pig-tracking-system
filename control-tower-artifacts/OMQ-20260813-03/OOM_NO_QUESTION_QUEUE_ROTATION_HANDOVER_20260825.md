# OMQ-20260813-03 no-question queue rotation handover

**DURABLY LOGGED — NOT YET AN OWNER OUTCOME**

- Finding: deployed no-question card suppression stopped Telegram delivery but
  returned no fresh reassessment time. The worker therefore retained an
  already-due timestamp, reclaimed the same first 20 cases every five minutes
  and could starve later cases.
- Classification: blocking defect/addendum in existing `OMQ-20260813-03`; no
  new mission, queue, scheduler, store or workflow.
- Exact owner outcome: no-question cases remain silent while every specialist
  case advances to a bounded next check and the existing 20-case worker limit
  rotates fairly. A later genuine question must still reach the owner once.
- Production evidence: exact loaded revision
  `edf34c5e2933a53b6ee49f15d3c9c4e9f5938a58`; natural cycles at
  `2026-08-25T14:25:25.463479Z`, `14:30:48.045256Z` and
  `14:35:20.461206Z` each claimed 20 and suppressed 20 with zero confirmed
  deliveries. `PIG-2026-3EE5` remained open at generation 11 with empty
  unknowns, overdue reassessment `14:25:25.463479Z` and unchanged last delivery
  `12:18:07.967276Z`.
- Repair: the existing suppression outcome now returns `now + CADENCE`; the
  canonical `_finish_claim` path persists that fresh time. Tests cover the
  exact timestamp and 21 due cases rotating through a 20-case claim cap across
  two cycles without provider delivery.
- Follow-up production finding: the first exact `e983221e` natural cycle at
  `2026-08-25T15:05:30.297550Z` still claimed and suppressed 20 cases. Event
  readback showed 19 `non_farm_case_delivery_suppressed` outcomes and one
  `manager_delivery_duplicate_suppressed`; neither older path supplied a fresh
  time, so the repaired HERDMASTER branch could not enter the capped queue.
- Invariant repair: `_finish_claim` now advances every successful unconfirmed
  outcome without an explicit future reassessment to `now + CADENCE`. Explicit
  future schedules remain authoritative; confirmed and failed outcomes retain
  existing behavior. The 21-case regression mixes all three observed
  suppression statuses and proves zero provider calls and complete rotation.
- Collision: PR `#1275` also edits the canonical mission register but does not
  edit this runtime or its focused tests. Register reconciliation must retain
  both receipts; no priority change.
- Acceptance remaining: independent review, exact-current CI, merge/deploy,
  exact loaded revision, natural queue rotation, case-specific suppression,
  a later genuine-question delivery and terminal-independent repetition.
- Owner action: none.

## Natural acceptance and confirmed-generation exception

- `9f2ba644d2263c3c8eec5892c6e3b48d96ec9988` was live at
  `2026-08-25T15:25:04Z`. Its natural `15:25:14.264025Z` cycle advanced all
  19 successfully suppressed cases to future reassessment with zero confirmed
  provider deliveries. The next natural cycle at `15:30:32.913131Z`, on
  descendant live revision `f8f7813510cccf19598073bf5b4d6cd6a1855e25`,
  processed 19 different suppression-event case IDs, advanced all 19 and again
  confirmed zero provider deliveries. Queue rotation is owner-outcome proven.
- One separate existing-lineage defect remains: confirmed generation 11 for
  `PIG-2026-3EE5` receives `manager_delivery_refresh_unavailable`. The monotonic
  confirmed-delivery guard correctly prevents a downgrade or resend, but used
  to return before releasing the lease or advancing reassessment. The case was
  therefore reclaimed each cycle with its last confirmed delivery unchanged at
  `12:18:07.967276Z` and its reassessment overdue from `14:25:25.463479Z`.
- This bounded addendum preserves confirmed truth, clears only the worker lease,
  schedules the next cadence and records that reassessment. It does not close
  the mortality case, manufacture evidence or send Telegram.

## Natural global-loop failure and bounded containment

**DURABLY LOGGED - NOT YET AN OWNER OUTCOME**

- Finding: after the monotonic repair was live, natural cycle
  `OOM-MANAGER-CYCLE-20260825T195518955722Z-2D05EA6CB69E4226B65044D88C45CFE1`
  finished the first Prince case safely, then claimed ROOTLINE mixer case
  `OOM-CASE-C0C589F1A0970494C2BB730F` and terminated with `ValueError` before
  finishing it. Exact read-only source reproduction identified
  `rootline_mixer_registry_binding_invalid` from the existing mixer-readiness
  collector. This one specialist case stopped every later due case, including
  `PIG-2026-3EE5`.
- Classification: blocking defect/addendum in the existing
  `OMQ-20260813-03` global manager loop. Priority is unchanged; it is being
  repaired now only because it blocks the already-active PIG acceptance.
- Collision result: retained PR `#1154` also touches
  `general_manager_worker.py`; its changes must not be silently combined.
  Register-only overlaps must retain both durable receipts.
- Bounded repair: contain `ValueError`, `RuntimeError` and `OSError` raised by
  one case's specialist refresh or delivery, while keeping `ManagerCaseError`
  and persistence/systemic invariants cycle-fatal. The affected case receives
  an attributable exception event, stable `waiting_reassessment`, a future
  five-minute cadence and a released lease. The cycle continues to later
  cases. No provider send, case close or farm-data mutation is manufactured.
- Proof boundary: disposable PostgreSQL covers faulty ROOTLINE first and a
  later silent HERDMASTER pig case, future cadence, lease release, exception
  attribution, immediate replay silence and zero sends. Source/tests/PR are
  not an owner outcome. Exact deployed revision plus natural mixed-case queue
  continuation and later terminal-independent repetition remain required.
- Owner action: none.
