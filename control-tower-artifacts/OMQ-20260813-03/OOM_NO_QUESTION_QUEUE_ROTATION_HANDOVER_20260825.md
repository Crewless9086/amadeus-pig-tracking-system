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
