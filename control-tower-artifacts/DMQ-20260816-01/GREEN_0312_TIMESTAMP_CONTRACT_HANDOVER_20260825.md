# DMQ-20260816-01 - GREEN timestamp-contract handover

Status: `DURABLY LOGGED - NOT YET AN OWNER OUTCOME` after reviewable commit.

## Production finding

The sole existing job `GREEN-WWS-WWS-20260825.r1.a79d4a6effa6` remained
`claimed` with no attempt, CUPS job or provider identity. GREEN 0.3.11 worker
`green-worker-bfd6ec117de944e3a9cb20e031c47af3` recovered the lease at
`2026-08-25T21:30:10Z`, after which the worker logged
`green_cycle_held reason=ValueError`.

The exact source path is:

1. PostgreSQL claim returns aware timestamp values.
2. `_public_job` passed them to Flask unchanged.
3. Flask JSON encoded them as RFC-1123 HTTP-date text.
4. `CanonicalClient.claim` called strict `parse_time`.
5. `datetime.fromisoformat` raised `ValueError` before `Ledger.put_claim`, PDF
   retrieval, an attempt identifier or CUPS.

## Bounded repair

- Serialize every public job timestamp as explicit UTC ISO-8601.
- Fail closed on a timezone-naive canonical timestamp.
- Classify a malformed worker timestamp as
  `canonical_timestamp_format_invalid` rather than a raw exception class.
- Bind the changed add-on package to immutable version 0.3.12.

## Containment and acceptance

This is the existing `DMQ-20260816-01` lineage. It creates no job, replay,
recovery request or direct production mutation. After review, merge, Render
deployment and immutable 0.3.12 publication, the same existing pre-attempt job
must be allowed to recover naturally. Business acceptance still requires one
canonical attempt/CUPS/provider result and genuine physical page observation;
source, deployment and package installation are not that outcome.

OWNER ACTION: NONE.
