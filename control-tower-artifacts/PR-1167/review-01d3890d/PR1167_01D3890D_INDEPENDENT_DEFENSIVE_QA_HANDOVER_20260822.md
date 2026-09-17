# PR #1167 exact-head independent defensive QA handover

## Verdict

**FAIL / CONTAINED — DO NOT MERGE OR DEPLOY.**

Candidate `01d3890d33f1341bcce5f9551ded858de4fd1833` is not class-complete for internal foreign-key enforcement triggers. The v4 catalog manifest records foreign-key definitions whenever either endpoint is governed, but records internal triggers only when the trigger's physical table is in the fixed `CATALOG_RELATIONS` list. A referenced-side enforcement trigger on non-governed `public.pigs`, for a governed `public.pig_welfare_cases` foreign key, can therefore be disabled without changing the manifest. Exact-head replay accepts the weakened catalog.

No repository source, PR, external system, deployment or production database was mutated. Testing used only the workspace-local disposable PostgreSQL runtime.

## Exact identity and collision audit

- Reviewed PR head: `01d3890d33f1341bcce5f9551ded858de4fd1833`.
- Original exact base: `8c517580bb03fd2036cfe359c403ebb55c43d5cf`.
- Current authoritative main observed during review: `c2fda06aa2748f5e16e0d3af79a0cf031027a648`.
- Main advancement from the original base changes only `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md` (348 inserted lines).
- Candidate source changes are `.github/workflows/oom-sakkie-audit-rails.yml`, `scripts/run_render_production_migrations.py`, `supabase/migrations/202608220002_allow_herdmaster_farrowing_protected_claims.sql`, and `tests/test_render_production_migration_rail.py`.
- Therefore the observed advancement is documentation-only and has no file collision with candidate source. If a repaired candidate later passes, it still requires rebase onto exact current main and exact-current gates before merge.

## Governance and skill preflight

- Read `.agents/skills/amadeus-operational-acceptance/SKILL.md` completely and applied its exact-revision, collision, failure-containment, replay and evidence contract.
- Requested root `AGENTS.md` is absent from both the exact isolated checkout and repository root. This is an explicit governance preflight gap; no remembered `AGENTS.md` rules were invented.
- Read the tracked active governance and the PR #1167 repair/current-main handovers, including the earlier rewrite-rule, view `_RETURN` rule and internal-trigger failures.

## Hosted and tracked evidence

GitHub reported four successful exact-head checks:

- `Closed Render migration rail with disposable Postgres` — pass, 50s.
- `Playwright real-browser behavior gate` — pass, 1m04s.
- `Unit tests with disposable Postgres audit rails` — pass, 2m14s.
- `charlie-core` — pass, 2m04s.

Fresh local exact-head tracked suite:

```text
RENDER_MIGRATION_TEST_DATABASE_URL=postgresql://postgres:***@127.0.0.1:55485/render_migration_rail_test
C:\Users\charl\venv\Scripts\python.exe -m unittest tests.test_render_production_migration_rail
Ran 25 tests in 132.720s
OK
```

The first invocation raced container initialization and was discarded; the identical command after PostgreSQL readiness passed.

## Independent reproduction — untracked referenced-side FK trigger

Runtime fixture: `.codex-runtime/missions/PR-1167/review-01d3890d/external_fk_trigger_attack.py`.

Procedure:

1. Reset the disposable database to the tracked predecessor fixture.
2. Run the exact-head rail successfully, producing five applied receipts and its checkpoint.
3. Select the DELETE-side internal FK trigger physically installed on `public.pigs` for constraint `pig_welfare_cases_pig_id_fkey` whose referencing relation is the governed `public.pig_welfare_cases`.
4. Capture `_catalog_snapshot()`.
5. Execute `ALTER TABLE public.pigs DISABLE TRIGGER <selected internal trigger>` and commit the attack.
6. Capture the manifest again and replay the exact-head rail.
7. Read receipt count and trigger state.

Exact result:

```text
selected_trigger=('public','pigs','RI_ConstraintTrigger_a_29757',
                  'pig_welfare_cases_pig_id_fkey',9)
catalog_digest_before=a529d7913c904cc323083aadd8e568c7a4ded191879783a246af85be45443fa7
catalog_digest_after_attack=a529d7913c904cc323083aadd8e568c7a4ded191879783a246af85be45443fa7
manifest_equal_after_attack=True
replay_error=None
replay_accepted=True
receipt_count_before=5
receipt_count_after=5
trigger_state_after_replay=D
```

This is a deterministic fail-open acceptance defect. The rail does not merely fail to diagnose the drift: it positively accepts replay while the FK enforcement trigger remains disabled. Receipt count stays stable only because replay is idempotent; it is not evidence of drift rejection.

## Root cause

`foreign_keys` selects a constraint when either its source or target relation belongs to `CATALOG_RELATIONS`. `internal_triggers`, however, selects solely on the physical trigger relation belonging to `CATALOG_RELATIONS`. PostgreSQL installs FK enforcement triggers on both referencing and referenced tables. Consequently, an FK that crosses the manifest boundary has only a partial enforcement-trigger inventory.

The tracked regression selects an internal FK trigger whose own physical relation is already in `CATALOG_RELATIONS`; it therefore cannot prove the external-counterpart case.

## Required repair and acceptance

Derive internal FK-trigger scope from the complete selected FK constraint set, not from the static relation list alone. For every selected foreign key, inventory every associated `pg_trigger` row by `tgconstraint`, regardless of whether `tgrelid` is itself a governed relation. Preserve the separate inventory for non-FK internal triggers on governed relations. Add a regression which deliberately selects a crossed-boundary FK and disables both referenced-side DELETE and UPDATE enforcement classes in independent cases; each must reject before any durable bootstrap/catalog/receipt change.

Also audit every allowlisted FK for both endpoints so this is class-complete rather than another object-name patch. The existing immutable checksum ledger plus separately governed baseline remains the right architecture; the repair belongs in the deterministic catalog-manifest drift gate, not in a new migration-specific semantic checker.

## What passed but does not override the failure

- Exact checksum-bound ordered allowlist and exact Render commit binding are covered and green.
- Tracked tests cover predecessor/target semantics, receipt identity, timezone invariance, replay, concurrency/advisory locking, full-transaction rollback, prior trigger/rule/view attacks, ACLs and owner checks.
- Static inspection confirms bootstrap, migrations, receipts, anchors, baselines and checkpoint mutations are enclosed in one transaction under a session advisory lock.
- The new reproduction proves the catalog gate is not class-complete, so those otherwise positive results cannot support operational acceptance.

## Unknowns and boundaries

- No production or provider readback was attempted or authorized.
- No deployment was attempted.
- The absent root `AGENTS.md` remains an Unknown/governance packaging defect.
- Numeric internal trigger names are disposable-database OIDs and are expected to vary; selection is semantic by constraint, endpoint table and DELETE event class.

## Check Receipt / Control Tower disposition

- Decision: **FAIL / contained**.
- Owner-visible production outcome: none; source review only.
- Protected actions performed: none.
- Rollback required: none; no candidate or external mutation occurred.
- Next owner action: none. Return to implementer with the bounded manifest-scope repair above.
- Merge/deploy status: forbidden pending repair, independent rerun, rebase to exact current main, and exact-current green gates.
