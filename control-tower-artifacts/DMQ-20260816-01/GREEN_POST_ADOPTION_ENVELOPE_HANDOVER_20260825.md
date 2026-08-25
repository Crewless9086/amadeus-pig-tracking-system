# DMQ-20260816-01 - GREEN post-adoption envelope handover

Status: `DURABLY LOGGED - NOT YET AN OUTCOME` after the reviewable commit.

Classification: existing-mission defect/addendum. Priority is unchanged.

Canonical production readback for
`GREEN-WWS-WWS-20260825.r1.a79d4a6effa6` proved authorization and retry
deadline remained current until `2026-08-25T22:00:00Z`, the exact
`green-0.3.2-20260822` device binding remained active, and attempt, CUPS and
provider identities remained null. `lease_recovered` events at
`20:33:32.786991Z` and `20:39:05.739689Z` proved the ordinary worker adopted
the same row. No PDF retrieval or state transition followed.

Cause: `Ledger.put_claim` hashed the complete returned canonical row, including
mutable lease fields. Lease rotation therefore changed the digest and raised
`job_identity_envelope_conflict` before the recovered row could be stored.

The bounded 0.3.11 repair compares a fixed immutable envelope projection and,
only when it is equal, atomically refreshes the stored full row, digest, lease
and timestamp. Any document, digest, retrieval, device, options or authorization
identity drift still fails closed. Existing ledgers are upgraded in place; no
new database, queue, job, replay or recovery workflow is introduced. A bounded
credential-free cycle-hold marker makes future failures reviewable without
printing tokens or envelopes.

Acceptance still requires reviewed merge, immutable image publication and
installation, then natural adoption of this same job before its existing
authority expires, one canonical attempt, exact CUPS/provider readback and
separate physical page confirmation. None of those are claimed here.

OWNER ACTION: NONE.
