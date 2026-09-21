# Consolidation publication and active admission repair — 2026-09-21

Status: current-state evidence, NON_DOCTRINE. Mission
`REPOSITORY-CONSOLIDATION-20260918`; sole coordinator
`CONTROL-TOWER-DESKTOP-SUCCESSOR-20260918`, task
`01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6`.

The owner approved each public draft separately:

- [PR1341](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/1341):
  `eff2ea1e8a1b4130e5c3febde7f608aff6b6f990`, preserving original eighteen
  commits through `013a9ebe23c3fedeedb285a88ad5103aad1d6a97`.
- [PR1342](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/1342):
  `66d5ec824b8a01f2e8e71fbcd931732fdc226288`, admission issuer correction and
  preparation for one paused Desktop mission registration.

All application gates passed on those exact heads: CORE, disposable PostgreSQL
audit rails, closed Render migration rail and browser behavior. PR1342 also
passed both real registration transaction tests: create/exact replay and full
rollback on event insertion failure. The signed admission gates remain failed.
Neither PR was merged or deployed. These results do not qualify later edits.

Explicit read-only canonical SQL at 05:16 UTC confirmed zero mission and event
rows for this consolidation. Two existing insert validation triggers reject
superseded pig identities; their definitions were inspected and retained.
An earlier options-only database connection reported read-only off through the
pooler; all its actual statements were SELECT and ROLLBACK. The subsequent
transaction explicitly set and verified READ ONLY. No production write occurred.

The one-time registration wrapper passed independent source review at SHA256
`f6951bf1d03f05174f35b4f8533573b66377da58b19313ed2c7f432208b07e1b` and twelve
offline tests. It remains preparation-only: genuine registration approval and
final exact package binding are still required. It is not part of the published
source or a deployed capability.

The missing step is a typed transition from the bootstrap repair candidate to
the original consolidation candidate. Existing first registration requires an
absent mission; the older candidate binder rejects paused state and uses Hermes
provenance. Keeping a consumed receipt in the current projection prevents
reissuance. Do not manufacture a different transport identity or change checks.

Charl directed active repair of this gap. One writer owns the existing Desktop
registration module, preparation CLI and tests in the continuing PR1342 worktree.
Prove the sequence through registration, issuance, predecessor merge evidence,
successor binding and reissuance, with replay, stale-state and rollback cases.
Preserve the original eighteen commits and all predecessor admission history.
Independent review and exact-head qualification precede publication/release.
Owner approval is not needed for this bounded local engineering work.

Provider readback at 05:37 UTC confirmed web revision
`3d321e4932cf205d03e759cc71a26edd411bc9d2`. Web/native-worker auto-deploy is off.
Seven repository cron services use automatic commit deployment, including one
suspended service. Any integration proposal must identify and contain those
effects; source merge alone is not live acceptance. Current main remains
`e46743cb3e8d224b60d17eb5920acb113f613a52`.

The earlier [retention receipt](../20260920/CONSOLIDATION_INTEGRATION_STATUS.md)
still proves physical preservation; its publication hold and unrun hosted-test
statements are superseded by this receipt. Working evidence and failed attempts
remain under `C:\Amadeus\.runtime\consolidation\integration-20260920\evidence`.
Sixteen publication/preparation artifacts were copied and hash-verified under
the existing recovery area in `integration-20260920\publication-20260921`.

The original agent outcome remains unproved. General-manager and domain work
resume after consolidation integration. No new farm, sales, payment, provider
send, hardware or worker-start authority follows from these source repairs.

Decision: YES — continue the bounded admission transition repair.
Why: an identified implementation gap, not waiting, prevents integration.
Send to exact terminal: CONTINUE—SEND NOTHING; this coordinator owns the work.
Expected business result: a preserved integrated baseline before agent acceptance.
OWNER ACTION: NONE while implementation and qualification continue.
