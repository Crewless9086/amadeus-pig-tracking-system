# DMQ-20260816-01 — GREEN 0.3.9 pre-attempt recovery addendum

Date: 2026-08-25  
Scope: the already-authorized weekly weighing-sheet job only

## Observed production boundary

- Home Assistant installed and restarted GREEN 0.3.9.
- Existing job `GREEN-WWS-WWS-20260825.r1.a79d4a6effa6` was claimed once at
  `2026-08-25T10:38:37.901744Z` by worker
  `green-worker-4cf210f99cbc40a9a78f610a15073af5`.
- Canonical readback remained `claimed`, with `attempt_id`, `cups_job_id`, and
  `provider_id` all null. Therefore no provider or physical print effect was
  established.

The worker had persisted the claim locally, but local recovery selected only
rows with an attempt identity. A PDF retrieval or digest-validation exception
before creation of that identity was reduced to the health file and left the
same canonical claim unable to resume.

## Repair contract

- Persist the bounded pre-attempt failure reason in the existing local recovery
  ledger; the ledger remains evidence only and never grants authority.
- Treat only `claimed` rows with both `attempt_id` and `cups_job_id` absent as
  pre-attempt recoverable.
- Renew or recover the same canonical lease, reconcile canonical state, and
  revalidate the immutable document/device/authorization bindings before one
  later attempt is permitted.
- Once an attempt exists, retain the existing ambiguity path. An ambiguous
  submission is never eligible for this recovery and cannot auto-reprint.
- This change creates no request, job, queue, authorization, or provider call.

Production-shaped tests cover retrieval failure, digest-validation failure,
expired-lease takeover, exactly one later CUPS submission, and exclusion of an
ambiguous provider outcome from automatic resubmission.
