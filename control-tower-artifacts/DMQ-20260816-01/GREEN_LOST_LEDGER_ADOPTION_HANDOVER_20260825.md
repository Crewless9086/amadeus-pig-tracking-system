# DMQ-20260816-01 - GREEN lost-local-ledger adoption handover

Status: `DURABLY LOGGED - NOT YET AN OUTCOME` in the reviewable commit carrying
this handover.

Classification: existing-mission defect/addendum. Priority is unchanged.

The sole canonical job `GREEN-WWS-WWS-20260825.r1.a79d4a6effa6` remained
`claimed` with an expired lease and no attempt, CUPS job or provider identity.
GREEN 0.3.10 was running with a fresh local ledger, so its retained-ledger
recovery path could not discover that canonical row. The earlier repair remains
authoritative for retained local rows; this change closes only the missing-local-
row discovery gap.

Migration `202608250002_adopt_green_lost_pre_attempt_claim` replaces the
existing canonical claim function. Under one row lock it may adopt the same
expired pre-attempt claim only when farm/GREEN scope matches, the immutable
device binding is active, and authorization and retry deadline remain current.
It creates no job and records a `lease_recovered` event with an explicit
lost-local-ledger marker. Live leases, post-attempt rows, inactive bindings and
expired authority are not eligible. A second worker receives no row after the
lease is renewed.

The migration is appended to the existing closed Render rail with exact LF
checksum, predecessor/target source and ACL checks, catalog inventory and
receipt readback. Production migration, lease adoption, submission and printing
are outside this source PR. After reviewed merge and governed migration proof,
the ordinary GREEN worker—not a direct recovery call—may adopt the same job and
continue the existing exactly-once path.

No new job, replay, duplicate document, direct stranded lease or physical print
claim is permitted. Canonical attempt/CUPS/provider evidence and the physical
page remain separately required before owner outcome.

OWNER ACTION: NONE.
