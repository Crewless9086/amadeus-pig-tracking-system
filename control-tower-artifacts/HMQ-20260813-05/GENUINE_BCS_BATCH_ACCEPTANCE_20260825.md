# HMQ-20260813-05 genuine selective-BCS batch acceptance

Status: `WORKING / GENUINE_BCS_BATCH_ACCEPTED / PREVIEW_PROJECTION_DEFECT_OPEN`

- Canonical bulk batch `df4c6197-4b2c-4253-b120-b07ad69305f4` completed with 79/79 successful weight rows, seven governed moves, zero failures and zero duplicates.
- Selective draft `BULK-DRAFT-1787650403572-8e45ea` recorded exactly five canonical BCS observations: Bonnie 3.5, Teena 2.0, Waki 2.0, Ms Piggy 3.5 and Zigay 3.0. Each row has its exact `bulk-bcs:{draft}:{pig}` idempotency identity and predecessor supersession.
- No active manager case is bound to any of the five exact pig references. The manually invoked read-only HERDMASTER projection consumed the observations with `writes_performed=false`; that is diagnostic evidence, not an automatic production outcome.
- Draft Preview omitted the selected BCS values. This is an owner-visible UI projection defect, not missing canonical data. The completed batch must not be resubmitted.
- Automatic worker-cycle processing, next follow-up, and later terminal-independent continuity remain unproven.
- Read-only probe: `.codex-runtime/missions/HMQ-20260813-05-BCS/latest_batch_acceptance_readonly.py`.

OWNER ACTION: NONE. Do not resubmit the accepted batch.
