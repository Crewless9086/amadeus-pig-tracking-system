# HERDMASTER Litter Supersession Source Handover

Status: source-only; no migration applied; no correction authorized

## Contract

Base `litters`, `pigs`, farm-event and audit rows are historical evidence and
are never deleted or rewritten. `current_canonical_litters`,
`current_canonical_pigs`, and `current_canonical_pig_state` exclude only rows
named by an owner-confirmed append-only supersession. The
`historical_litter_representations` view retains both representations and the
supersession lineage.

The service requires exact retained/superseded litter IDs, exact retained and
superseded child allowlists, deterministic packet identity, durable matching
owner authorization, reference and skipped-audit digests, SERIALIZABLE and row/
advisory locks. Replay of the identical committed packet creates zero rows.
Only a PostgreSQL `service_role` session (or a role PostgreSQL has authorized to
`SET ROLE service_role`) may invoke the SECURITY DEFINER append function.
Callers cannot insert directly into any of the five correction evidence tables.

Once a child disposition exists, database triggers reject update/delete of that
base pig and reject a new pig/animal/child reference in every inventoried public
base table, including embedded JSON. Superseded litter rows likewise reject
update/delete. These guards preserve the correction as an overlay: the twenty
base child identities, both litter rows, and the ninety skipped audit rows
remain visible to explicit history/audit reads and remain immutable.

## Consumer inventory

| Consumer | Current/history decision |
|---|---|
| `farm_supabase_read_service` current animal, allocation, litter register, litter overview, breeding snapshot and observation reads | changed to authoritative current views; joins to base `pigs` only enrich an already-filtered canonical ID |
| daily weight-event register and tag lookup | explicit historical event/identity lookup; existing events remain visible, while triggers reject new events for disposed identities |
| HERDMASTER breeding attention/operating loop | receives current rows through the farm read service |
| Oom Sakkie herd questions and worklists | receives current rows through HERDMASTER/farm readers |
| reporting litter attention | receives current litter overview |
| litter profile/current operational screens | receive current litter overview and current children |
| mating analytics | receives current litter overview; immutable mating linkage remains base evidence |
| litter/pig, breeding-observation and purpose write workflows | retain base-table targets for valid current IDs; database guards fail closed for disposed IDs and superseded litters |
| auction-list and sales transaction locks | retain base identity locks; downstream member/order/state writes are database-guarded, so disposed IDs cannot enter a new transaction |
| loading sheet, meat production and sale projections | changed to canonical current state before availability-bearing use |
| migrations, import/recovery and audit tools | intentionally retain base/history access |

Direct base reads are not automatically “current.” New owner-facing or
recommendation consumers must use the current views or the canonical farm read
service. Historical/audit consumers must name that intent explicitly.

## Later integration and proof

1. Reconcile the PR against current main and rerun exact-head CI.
2. Rehearse the migration in disposable PostgreSQL.
3. Prove every current consumer sees one litter and ten retained children while
   history sees both representations and all twenty identities.
4. Generate the exact reference allowlist and 90-row skipped-audit IDs/digests.
5. Obtain independent herd/data-integrity and backend/security approval.
6. Merge and deploy only in an assigned HERDMASTER release window.
7. Produce the exact owner preview from
   `C:\tmp\herdmaster-zigay-exact-correction-preview-20260730.md`, hash its
   canonical UTF-8 payload, and bind the exact hash, operation ID and owner
   principal in `litter_correction_authorizations`. If confirmation is
   withdrawn before execution, append a matching authorization revocation.
   Do not write correction metadata before Charl confirms the preview.
8. Build the governed service packet from live locked rows: retained and
   superseded litter IDs; mating ID; both exact ten-child allowlists; the
   schema/reference inventory digest; all ninety skipped row IDs/count/digest;
   input digest; authorization ID; and preview hash.
9. Apply once through a true `service_role` database session. The expected
   metadata delta is 101 append-only rows: one supersession, ten child
   dispositions and ninety audit-evidence bindings. Base farm-fact delta is
   zero. Verify replay creates zero rows,
   verify unrelated digests remain unchanged, and release runtime immediately.

No Zigay identity is embedded in the implementation.

## Prepared verification

- Focused rail contract, consumer, read/write cutover, litter, breeding,
  auction/sales, loading and meat suites: 177 passing.
- Complete Oom Sakkie service suite: 315 passing, 7 environment-dependent
  skips.
- Disposable PostgreSQL proof: 5 passing against an isolated PostgreSQL 16
  container, which was removed after the run. It covers service authority, exact retained
  and disposed ten-child cohorts, the ninety skipped rows, concurrent
  create/replay, digest rollback, one-current/two-history projections, blocked
  post-disposition writes and unchanged unrelated identity counts. It runs when
  `CHARLIE_DISPOSABLE_POSTGRES_URL` is supplied and otherwise skips without
  contacting shared infrastructure.
