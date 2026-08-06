# CHARLIE CORE atomic many-to-one replacement handover

Status: source-only candidate. No production migration, successor, binding,
approval, pickup, merge, deployment, Telegram action or runtime activation is
authorized by this document.

## Outcome and boundary

The existing `charlie_missions` queue gains one additive, append-only
replacement ledger. One fully bound paused successor and every immutable
predecessor binding are committed by one serializable security-definer
function. This is not a queue, dispatcher or operational agent. Ordinary farm
work remains with Oom Sakkie and deployed specialists.

Migration must precede application deployment. Code that references the ledger
fails closed if the additive tables are absent. Production application of the
migration, credential provisioning and any replacement execution each require
their own exact owner authorization.

## Source map

- contract, digest, HMAC authorization and mission-store adapter:
  `modules/charlie/mission_replacement.py` exported by
  `modules/charlie/mission_store.py`;
- additive PostgreSQL enforcement:
  `supabase/migrations/202608020001_create_charlie_many_to_one_replacements.sql`;
- governed operator CLI: `scripts/charlie_many_to_one_replacement.py`;
- unit enforcement: `tests/test_charlie_mission_replacement.py`;
- disposable PostgreSQL enforcement:
  `tests/test_charlie_mission_replacement_postgres.py`.

## Exact later command contract

Prepare is read-only and emits the deterministic identities to review:

```powershell
python scripts/charlie_many_to_one_replacement.py prepare `
  --contract C:\tmp\s01-successor-contract.json `
  --predecessors C:\tmp\s01-predecessor-allowlist.json
```

The owner-admin surface validates the HMAC and records the exact signed envelope
through a separately provisioned login that may assume only the NOLOGIN
`charlie_mission_replacement_authorizer` capability role:

```powershell
python scripts/charlie_many_to_one_replacement.py authorize `
  --contract C:\tmp\s01-successor-contract.json `
  --predecessors C:\tmp\s01-predecessor-allowlist.json `
  --authorization C:\tmp\s01-owner-authorization.json
```

Only after that grant is durably readable may an operator run:

```powershell
python scripts/charlie_many_to_one_replacement.py execute `
  --contract C:\tmp\s01-successor-contract.json `
  --predecessors C:\tmp\s01-predecessor-allowlist.json `
  --authorization C:\tmp\s01-owner-authorization.json `
  --confirm-exact-transaction-digest <64-lowercase-hex>
```

Authorization recording requires
`CHARLIE_MISSION_REPLACEMENT_AUTHORIZER_DATABASE_URL`; execution requires
`CHARLIE_MISSION_REPLACEMENT_DATABASE_URL`. Each is a separately provisioned
login granted only its corresponding NOLOGIN capability role. HMAC validation
uses a separately controlled `CHARLIE_MISSION_REPLACEMENT_AUTH_SECRET` of at
least 32 characters. Service role, browser roles and the replacement writer
cannot issue authorization; the authorizer cannot execute replacement. The
configured `CHARLIE_MISSION_REPLACEMENT_OWNER_IDENTITY_HASH` must exactly match
the signed envelope's owner identity. The
callable application contract is
`mission_store.execute_many_to_one_replacement(contract, predecessors,
authorization)`.

## Required contract and authorization payloads

The successor contract contains the normal mission fields, exact `status:
paused`, complete adaptive orchestration packet/workflow and validated binding.
The predecessor allowlist is sorted and each item contains:

```json
{
  "mission_id": "...",
  "expected_status": "new|triaged|planned|blocked|pr_ready|paused",
  "expected_content_digest": "<sha256>",
  "expected_metadata_generation": "<exact generation>",
  "unfinished_value_reference": "artifacts/03_preserved_unfinished_value_manifest.json#..."
}
```

The owner authorization is valid for at most 15 minutes and contains exactly:

```json
{
  "version": "charlie_many_to_one_replacement_v1",
  "replacement_identity": "CHARLIE-REPLACEMENT-BATCH-...",
  "contract_digest": "<sha256>",
  "predecessor_set_digest": "<sha256>",
  "transaction_digest": "<sha256>",
  "owner_identity_hash": "<sha256>",
  "issued_at": "<UTC ISO-8601>",
  "expires_at": "<UTC ISO-8601>",
  "signature": "<HMAC-SHA256>",
  "authorization_digest": "<sha256 of signed payload>"
}
```

Any changed byte produces a different digest and requires a new owner
authorization. Authorization creates no activation authority.

## Before and after proof queries

Run before in one read-only session and archive the result:

```sql
select mission_id,status,
       public.charlie_mission_replacement_content_digest(m) content_digest,
       public.charlie_mission_replacement_metadata_generation(m) metadata_generation,
       metadata_json
from public.charlie_missions m
where mission_id = any(:exact_predecessor_ids)
order by mission_id;

select predecessor_mission_id,successor_mission_id,replacement_identity
from public.charlie_mission_replacement_bindings
where predecessor_mission_id = any(:exact_predecessor_ids);
```

The second result must be empty. After execution, archive:

```sql
select mission_id,status,metadata_json->'many_to_one_replacement' replacement
from public.charlie_missions where mission_id=:successor_id;

select predecessor_mission_id,expected_status,expected_content_digest,
       expected_metadata_generation,predecessor_snapshot_json,
       unfinished_value_reference
from public.charlie_mission_replacement_bindings
where replacement_identity=:replacement_identity order by predecessor_mission_id;

select event_type,mission_id,transaction_digest,evidence_json,created_at
from public.charlie_mission_replacement_audit_events
where replacement_identity=:replacement_identity order by created_at,mission_id;
```

Also capture these global invariants before and after, using the same snapshot
boundary:

```sql
select status,count(*) from public.charlie_missions
where status in ('new','triaged','planned','approved','in_progress','blocked','pr_ready','release_approved','paused')
group by status order by status;

select mission_id,status from public.charlie_missions m
where status in ('approved','in_progress','release_approved')
  and not exists(select 1 from public.charlie_mission_replacement_bindings b where b.predecessor_mission_id=m.mission_id)
order by mission_id;

select mission_id,status,public.charlie_mission_replacement_content_digest(m) content_digest
from public.charlie_missions m
where mission_id='CHARLIE-REPLACEMENT-AF110E2A071BC18CCAA00DF2';
```

The before snapshot is 86 nonterminal rows (55 new, 27 paused, three blocked,
one pr_ready), an empty runnable set, and the unchanged historical T0 canary.
After an authorized S01 replacement there are three immutable predecessor
bindings and one additional paused successor; the old 86 rows and their status
distribution remain unchanged. Record `git rev-parse origin/main` and the
trusted Render deployed commit alongside both snapshots; the source baseline
for this candidate is `70a4cf2b235e5ba441f9b5901efa45e699ad0c0b`.

The successor must be `paused`; binding count must equal the reviewed allowlist;
the full signed authorization envelope is readable from the append-only grant,
batch and audit evidence; snapshots/artifacts remain readable; every authoritative pickup query must
exclude all predecessors. Exact replay returns the stored result with
`replayed=true`, `rows_changed=0`.

## Rollback evidence

Disposable PostgreSQL injects a trigger failure on the third binding. The
function returns rejection and post-query proves zero successor, zero bindings
and zero audit rows. Missing/changed predecessors, duplicate IDs, conflicting
bindings, successor collision, stale/forged authorization and unsupported
statuses show the same zero-mutation result. Serializable concurrent exact
calls produce one create and one replay. Bound predecessor rows reject future
updates and all replacement history tables reject update/delete.

## S01 procedure (not authorized now)

The future reviewed S01 contract must remain `paused` and name only:

- `CHARLIE-OUTCOME-23890E45EFE2A2C3`;
- `CHARLIE-FOLLOWUP-672D7917CFD7332D`;
- `CHARLIE-FOLLOWUP-TELEGRAM-CHANNEL-CONTRACT-20260722`.

Read exact status/digest/generation, prepare the deterministic transaction,
obtain owner authorization for that exact payload, rerun the before proof,
then execute once. Commit creates S01 paused and retires all three predecessors
atomically. Failure leaves all three existing predecessors unchanged and the
successor absent. A separate later owner decision is required to approve or
activate S01.

Accepting S01 does **not** accept the other six proposed successors and does
**not** resolve any of the four decisions in
`artifacts/11_owner_decisions_required.md`.
