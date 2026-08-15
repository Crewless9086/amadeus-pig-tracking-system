# Oom Sakkie specialist dispatch acknowledgement handover

Status: SOURCE-READY / ZERO-I/O / NOT INTEGRATED

## Outcome

`modules/oom_sakkie/specialist_dispatch_ack.py` provides one pure reducer for
honest specialist-dispatch status. A release request or release ledger event no
longer has any semantic path to `started` without separate evidence from the
exact named worker for the exact mission and release digest.

The contract performs no reads, writes, worker wake-up, polling, Telegram,
n8n, Render, configuration or runtime action. It is deliberately not wired to
any production adapter in this source-only mission.

## Durable state model

| State | Minimum evidence |
|---|---|
| `release_requested` | Exact mission, target worker and SHA-256 release digest |
| `released` | Matching release plus acknowledgement and start deadlines |
| `delivery_acknowledged` | Matching durable delivery receipt before its deadline |
| `started` | Matching acknowledgement plus named activity, heartbeat and trusted observation receipt proving it was fresh before the start deadline |
| `progress_observed` | A valid start plus later matching activity whose heartbeat was fresh at its trusted observation receipt |
| `completed` | A valid start plus an exact outcome artifact identity, SHA-256 and outcome status |
| `contained` | Matching explicit containment evidence; never completion |
| `ack_timeout` | Derived when acknowledgement or valid start evidence misses its deadline |

Every snapshot keeps `automatic_resumption_claimed`, worker calls, Telegram
calls and writes false. An unrelated worker, mission or release digest is
ignored and reported; it cannot advance the target dispatch. A stale or
future heartbeat cannot prove execution. `activity_observed_at` separates a
heartbeat accepted while fresh from raw activity first discovered after it
became stale; a valid historical start and completion therefore do not decay.

## Alert contract

One timeout creates one deterministic `specialist_dispatch_ack_timeout` alert
identity bound to:

- mission identity;
- exact target worker identity;
- release digest; and
- either `delivery_acknowledgement_missing` or `start_not_observed`.

Re-evaluation and duplicate release events reproduce the same alert identity,
so a future persistence adapter can upsert/edit one buttonless systemic alert
instead of producing repeated clutter. The pure contract itself sends nothing.
It sets `manual_coverage_required=true` and
`automatic_resumption_claimed=false`.

## BEACON PR #647 regression

The focused suite models the observed failure precisely: Oom Sakkie can record
a correct release while the visible BEACON worker provides neither delivery
acknowledgement nor start evidence. The result is `ack_timeout`, never
`started`; replay produces the same release/alert identities and no duplicate
semantic effects.

Additional coverage proves:

- a release event never implies execution;
- acknowledgement remains distinct from start;
- stale activity cannot prove start;
- another worker or mission cannot satisfy the dispatch;
- progress requires a valid start and fresh matching activity;
- a completion assertion without an outcome artifact is ignored;
- containment is not completion;
- duplicate events are no-ops and conflicting event-ID reuse fails closed; and
- every state preserves zero-I/O authority.

## Files

- `modules/oom_sakkie/specialist_dispatch_ack.py`
- `tests/test_oom_sakkie_specialist_dispatch_ack.py`
- `docs/06-operations/OOM_SAKKIE_SPECIALIST_DISPATCH_ACK_HANDOVER.md`

## Verification

Focused command:

```powershell
C:\Users\charl\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_specialist_dispatch_ack -v
```

Expected: 18 focused tests pass. The adjacent owner-attention regression set
plus this contract runs 70 tests successfully.

## Independent review

- Operations/CX: `APPROVE`. Confirmed release/execution honesty, durable
  historical completion, stale-first-observation rejection and uncluttered
  alert semantics.
- Backend/security/privacy/authority: `APPROVE`. Confirmed exact identity and
  chronology binding, trusted observation receipt, replay/conflict behavior,
  artifact-gated completion, deterministic alert deduplication and zero I/O.

## Deferred integration boundary

A later separately claimed integration may map append-only ledger records into
`DispatchEvent`, persist the returned snapshot, and upsert the deterministic
alert. That adapter must:

1. preserve exact mission/worker/digest bindings and both deadlines;
2. obtain delivery acknowledgement from the named worker rather than the
   release writer;
3. stamp `activity_observed_at` at a trusted ingestion boundary and prove the
   matching heartbeat was fresh at that receipt; never trust a worker-supplied
   observation timestamp;
4. persist at most one alert per returned deduplication key;
5. require an immutable outcome artifact before completion;
6. never wake a terminal, claim automatic resumption, send Telegram or mutate
   runtime merely because `released` exists; and
7. add adapter-level transactional/replay tests before deployment.

No ROOTLINE, HERDMASTER health/loss, production adapter, Telegram, n8n, Render,
configuration, registry, route or runtime file was modified here.
