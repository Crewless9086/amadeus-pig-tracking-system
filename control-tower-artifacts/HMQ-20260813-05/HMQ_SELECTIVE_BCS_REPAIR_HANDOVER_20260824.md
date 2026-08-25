# HMQ-20260813-05 selective BCS repair handover

- Existing lineage: HMQ-20260813-05 / HMQ-00.
- Authority: existing Control Tower mission register; no new doctrine.
- Base: exact authoritative main `2fdecec1444725d07e0b362dc95caaa3c6e99ea6`.
- Collision: no active PR owns the changed Bulk Weight Entry or observation route; stale PR #603 remains non-authoritative and unmerged.
- Reuse: existing Bulk Weight Entry, strict owner-admin boundary, and canonical Herdmaster breeding observation writer.
- Effects: optional BCS-only rows create separate canonical observation events; blanks do nothing; deterministic draft/pig replay and append-only supersession are preserved.
- Exclusions: no heat field/work, schema, store, queue, provider action, farm mutation, mating, lifecycle or availability effect.
- Acceptance: source/tests are not owner outcome. Release, genuine bulk capture, separate canonical readback, replay proof and downstream management projection remain required.

## 2026-08-25 genuine batch acceptance addendum

- Batch `df4c6197-4b2c-4253-b120-b07ad69305f4` completed: 79 weight rows, seven moves, 79 successes, zero failures and zero duplicates.
- Draft `BULK-DRAFT-1787650403572-8e45ea` created exactly five idempotent canonical observations: Bonnie 3.5 (`HERD-OBS-5F9A52DC43BA509393A2A6A189231CDC`), Teena 2.0 (`HERD-OBS-22388C055CF15234B27AAEB757726210`), Waki 2.0 (`HERD-OBS-C59CE145C1F257D5B996BBFD69D77A10`), Ms Piggy 3.5 (`HERD-OBS-E0CED0A5325E5D1F8D30854BE55ACDBD`) and Zigay 3.0 (`HERD-OBS-BB5068789C07574EBBF0B571C5144CF3`).
- Exact-pig manager-case readback returned zero rows. A manually invoked read-only operating-loop projection consumed the facts with `writes_performed=false`; this is not proof of an automatic deployed worker, next follow-up, or later terminal-independent continuity.
- The Draft Preview omitted BCS values. Canonical data is present, so the batch must not be resubmitted. The preview projection and automatic closed-loop evidence gaps are same-lineage defects/addenda.
- Status: `WORKING / GENUINE_BCS_BATCH_ACCEPTED / PREVIEW_AND_AUTOMATIC_FOLLOW_UP_UNPROVEN`. OWNER ACTION: NONE.
