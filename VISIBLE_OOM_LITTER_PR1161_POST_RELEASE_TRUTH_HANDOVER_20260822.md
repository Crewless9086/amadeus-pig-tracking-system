# Control Tower Feedback — PR #1161 post-release truth

## Governance preflight

- Read-only truth worktree: `C:\tmp\oom-pr1161-independent-rereview-7a69dd4f`
- Starting review handover `HEAD`: `7bf85dd6562e74f6be0065d0cc2d01b07f6110e2`; reviewed release merge: `a6b3112fe3a3008af763685e5b1ca31ab814963f`.
- Mission Standard: present, tracked in this worktree lineage, blob `3002b94713e286c4eb2019419c438cc378c337fa`, SHA-256 `44E34C69145B83D2CD5B6A5322A6C2C124789FA647E19F19B3E39A7293A5202B`, 1,127 lines; previously read completely in this same retained review lane and identity reverified before this audit.
- Authority: read-only repository, GitHub and public production health/revision inspection. No provider request, historical replay, protected claim, farm/customer write, migration, deployment or configuration mutation.

## Independent disposition

**FAIL — deployed code is not ready for a genuine owner farrowing event.**

**NO BUSINESS OUTCOME.** Merge and loaded source are technical release evidence only. The database authority rail needed to create the protected confirmation claim is not represented by the merged migrations, and the new fact-correction migration has no governed production-application path or readback evidence.

## Exact production and lineage truth

- PR #1161 merged at `a6b3112fe3a3008af763685e5b1ca31ab814963f`.
- Public `GET /health/revision` returned HTTP 200 with provider `render`, `identity_complete:true`, and loaded revision `429a91ffd3dd4f38faadeb9fb0f19f202ea87537`.
- Loaded revision `429a91ff` is a descendant of merge `a6b3112f`; its history contains the exact reviewed source head `7a69dd4f`.
- Public `GET /health` returned HTTP 200 and `{"status":"ok"}` on the confirming retry. An earlier isolated request returned a transient Cloudflare 502; health recovered without terminal action.
- Loaded revision is not the current Git main (`fbd49b3c...` at audit time), but later main commits are documentation/Green lineage. This does not remove the blocker below.
- The semantic front-door source gate is deployed in ancestry, but its production environment state (`OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED`, model and API-key configuration) is not exposed by the read-only health surfaces and remains **Unknown**. No owner/provider request was fabricated to infer it.

## Release-blocking schema/authority findings

### 1. Protected action kind is absent from every database constraint migration

- Source calls `create_claim(action_kind="herdmaster_record_farrowing_litter", ...)` from `modules/oom_sakkie/herdmaster_farrowing_runtime.py`.
- The latest constraint definition in `supabase/migrations/202608210001_create_green_print_jobs.sql:36-43` admits mortality, grouped weights, breeding, ROOTLINE, SAM, BEACON and Documents/Green kinds, but **does not admit `herdmaster_record_farrowing_litter`**.
- Repository-wide search finds the new action kind only in runtime Python/tests, never in a migration that alters `oom_protected_action_claims_action_kind_check`.
- Therefore, against the repository-defined production schema, a genuine farrowing preview reaches `create_claim` and its insert is rejected by the database check constraint. The gateway has no usable confirmation claim/card, so no exactly-once protected litter action can begin.

### 2. Migration `202608220001` is absent from the closed Render allowlist

- `supabase/migrations/202608220001_extend_litter_supersession_for_fact_corrections.sql` exists with filesystem SHA-256 `27182e8c13cb45db465e1c818cc0578f56547427a3607b0371595f3448b590c0`.
- It changes the supersession reason constraint/function and inserts migration-log ID `202608220001_extend_litter_supersession_for_fact_corrections`.
- `scripts/run_render_production_migrations.py` is a closed append-only allowlist and currently ends with migrations `202608190002`, `202608200001`, and `202608200002`; it contains no `202608220001` item or checksum.
- No local `DATABASE_URL` or `SUPABASE_DB_URL` was available, and public health does not expose schema truth. Consequently there is **no canonical production readback evidence** for:
  - the migration-log row;
  - the updated `litter_supersessions_reason_check` admitting `fact_correction`;
  - the deployed `validate_litter_supersession()` function definition;
  - or the missing protected-action-kind constraint.
- The only governed Render migration rail visible in loaded source cannot apply `202608220001`; claiming it applied would be unsupported even if the SQL file shipped in the image.

## Consequence and containment

- New non-correction and correction farrowing journeys both require the missing protected action kind, so this is not merely an optional correction limitation.
- Correction journeys additionally require verified `202608220001` schema/function state.
- Do not ask Charl or family to submit a genuine farrowing report yet. Do not replay Pig 161, Linda, or any historical event. The first genuine event must remain unconsumed until the reusable database release defect is corrected, deployed and read back.
- This is a technical defect and routine governed release repair, not an owner factual or physical blocker.

## Required repair acceptance

1. Add one reviewed migration that safely replaces `oom_protected_action_claims_action_kind_check` while preserving every current allowed action and adding `herdmaster_record_farrowing_litter`.
2. Add `202608220001` and the new action-kind migration to the closed Render production migration allowlist with exact canonical LF SHA-256 values and ordered identities.
3. Extend migration-rail/disposable-Postgres tests to prove both constraints, the updated validation function, migration-log entries, checksum binding, idempotent re-run and append-only receipts.
4. Independently review exact repair head, merge through the serialized release lane and execute only the closed Render migration rail bound to the exact loaded commit.
5. Obtain canonical readback of production migration receipts/log IDs, `pg_get_constraintdef` for the action-kind and supersession constraints, and `pg_get_functiondef(public.validate_litter_supersession())`; compare identities/digests to reviewed source.
6. Verify `/health/revision` at the repair descendant and the semantic feature-gate/configuration state through a safe authenticated operational-status surface or protected environment inspection without sending an owner message.
7. Only then mark the deployed agent `event-waiting` and allow one later genuine owner/family event. Retain the same mission through provider confirmation, exactly-once canonical action/readback, HERDMASTER follow-up and a later terminal-independent cycle.

## Compact lifecycle block

```text
Mission lifecycle state: WORKING
Owner-visible outcome: one genuine natural farrowing report becomes one exactly-once canonical litter with provider-visible completion and HERDMASTER follow-up
Technical stage reached: PR merged; reviewed source loaded in Render ancestry; public health/revision healthy
Deployed-agent state: deployed-defective for farrowing claim creation; not ready for genuine event
Web/API runtime: Render revision 429a91ffd3dd4f38faadeb9fb0f19f202ea87537, HTTP 200 health/revision
Autonomous trigger: authenticated Telegram event path exists in source; semantic production gate state Unknown
Worker/scheduler: event-driven web runtime; independent worker/heartbeat not separately proven
Last independent cycle: none for repaired farrowing path
Next automatic cycle: schema/authority repair review -> merge -> closed Render migration -> canonical schema readback -> event-waiting
Terminal independence: web remains deployed, but farrowing path cannot safely accept a genuine event
Last terminal-invoked cycle: read-only HTTP health/revision only
Provider/canonical/physical evidence: no provider/farm event; production schema readback unavailable
Remaining acceptance journey: database repair through genuine deployed event, canonical/provider closure, follow-up and later independent cycle
Exact hold and unblock condition: missing action-kind migration and governed 202608220001 application/readback
Safe work exhausted before hold: yes for read-only diagnosis; source repair and protected migration execution require assigned implementation/release lanes
Owner repetition requested: no
Terminal/worktree closeout: released-retain after durable handover commit
```

**Decision: NO**

**Why:** A genuine event would hit a database constraint before protected confirmation, and the required correction migration is not governably applied or proven.

**Send this exact prompt to OOM SAKKIE/HERDMASTER DATABASE RELEASE REPAIR TERMINAL:** Continue the existing PR #1161 outcome-bound mission; do not restart or replay any animal event. From current main in a clean isolated source worktree, add a migration that preserves every currently allowed `app_private.oom_protected_action_claims.action_kind` and admits `herdmaster_record_farrowing_litter`; add both `202608220001_extend_litter_supersession_for_fact_corrections` and the new action-kind migration to the closed `scripts/run_render_production_migrations.py` allowlist with exact LF SHA-256 identities. Add disposable-Postgres and migration-rail tests proving constraint/function/log state, checksum binding, append-only receipts and idempotent rerun. Obtain independent exact-head review, then use the serialized release lane to merge, deploy and run only the closed Render migration rail bound to the exact loaded commit. Return canonical production readback for migration receipts/log rows, both relevant constraint definitions and `validate_litter_supersession()` function identity, plus `/health/revision` and semantic feature-gate/configuration truth. Make no Telegram replay, protected confirmation, farm/customer/provider mutation or fabricated event. After schema proof passes, automatically reclassify the same mission as event-waiting for one later genuine owner/family report and retain it through exactly-once canonical/provider completion, HERDMASTER follow-up and a later terminal-independent cycle.

**Expected business result:** The next genuine farrowing report reaches a valid protected confirmation and can be recorded exactly once instead of failing at the database authority boundary.
