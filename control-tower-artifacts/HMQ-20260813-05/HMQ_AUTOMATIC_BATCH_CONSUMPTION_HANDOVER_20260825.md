# HMQ-20260813-05 automatic batch consumption handover

- Existing mission only: `HMQ-20260813-05` / `HMQ-20260813-00`.
- Classification: existing-mission activation and natural acceptance.
- Reused runtime: existing five-minute Oom Sakkie general-manager worker and
  canonical `app_private.oom_manager_cases` lifecycle.
- Input boundary: completed `bulk_weight_batches`, their exact
  `pig_weight_events`, and exact `pig_observation_events` keyed by the accepted
  draft/pig identity.
- Output boundary: one stable BCS case and one stable material-weight case per
  exact pig, using only the deterministic latest qualifying canonical event
  across completed batches, with exact evidence references, generation/idempotency protection,
  bounded reassessment, and terminal completion only from newer qualifying
  canonical evidence.
- Preserved safeguards: read-only collection, no heat inference, no diagnosis,
  no batch replay, no new queue/store/schema/scheduler, no provider or farm
  effect during source preparation.
- Source/release: PR `#1270` independently reviewed PASS and merged as
  `8465103df799acd7b6225c8c98440ccb4cfa05b5`; Render loaded that exact revision.
- Natural activation: terminal-independent cycle
  `OOM-MANAGER-CYCLE-20260825T121524106342Z-E5A83E83364E4A2D90C67A6F924FEE71`
  consumed genuine accepted batch `df4c6197-4b2c-4253-b120-b07ad69305f4`
  at `2026-08-25T12:15:24.106342Z` and created seven stable exact-pig cases.
- Canonical readback: Teena BCS 2 (`OOM-CASE-D2D021AD952D54D4EBB16689`),
  Waki BCS 2 (`OOM-CASE-06F41E4EF440CC20585E312C`), tag 138 -20.0%
  (`OOM-CASE-FF00ED3DB3A385AE091C08EF`), tag 139 -10.6%
  (`OOM-CASE-C9695FF2BE2A3A3C1BF4A52E`), tag 111 -10.3%
  (`OOM-CASE-C1A2AB12E9C1A2D664B32A4B`), tag 2 +15.6%
  (`OOM-CASE-BDE56DBB892229C103AC8541`), and Ms Piggy -22.6%
  (`OOM-CASE-1FB5B5C3B6F7C36E412265F5`). Each remains open at generation 1
  with exactly one append-only `created` event and a bounded reassessment.
- Later independent proof: cycles from `2026-08-25T12:20:28.858735Z` through
  `2026-08-25T13:40:23.087785Z` loaded the same revision, created zero new
  cases and retained these seven at generation 1 with unchanged evidence digest
  and `updated_at=2026-08-25T12:15:24.106342Z`.
- Heat-free proof: the collector contains no heat input or dependency; no heat
  case, question, task, reminder, confidence penalty or blocker was created.
- Owner outcome: `OWNER OUTCOME PROVEN` only for completed-batch-to-management
  activation and later terminal-independent idempotency. The seven material
  cases remain open follow-up; their later animal outcomes are not claimed.
- Owner action: none.
