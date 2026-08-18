# Zigay litter supersession — revised exact preview contract

Status: source-ready; no confirmation requested; no correction executed

## Owner decision preserved

Charl's existing decision is unchanged:

> Retain `LIT-2026-B1A8` and its ten child identities as the canonical
> Zigay/Bola farrowing. Preserve `LIT-2026-A523` and its ten generated child
> identities as superseded history without deletion, reparenting, identity
> merging or pairwise child matching.

The revised rail changes only how immutable SAM review snapshots are
classified. It does not change the biological or disposition meaning of the
confirmed preview, so duplicate owner confirmation is not required.

## Exact current before-state contract

- Current Zigay July 2026 litter representations: 2.
- Retained litter: `LIT-2026-B1A8`.
- Superseded litter: `LIT-2026-A523`.
- Retained mating: `MAT-2026-6552E7`.
- Retained B1A8 children:
  - `PIG-2026-0F1F`
  - `PIG-2026-3F59`
  - `PIG-2026-6190`
  - `PIG-2026-8C84`
  - `PIG-2026-96CC`
  - `PIG-2026-C124`
  - `PIG-2026-C1FD`
  - `PIG-2026-D69F`
  - `PIG-2026-E65E`
  - `PIG-2026-F555`
- Superseded A523 identities:
  - `PIG-2026-1907`
  - `PIG-2026-1AC2`
  - `PIG-2026-74E4`
  - `PIG-2026-7C56`
  - `PIG-2026-8D0B`
  - `PIG-2026-9BDA`
  - `PIG-2026-D047`
  - `PIG-2026-D25C`
  - `PIG-2026-D7CF`
  - `PIG-2026-F202`
- A523 active/on-farm identities: 9.
- B1A8 current live identities: 7.
- B1A8 mortality evidence: one stillborn and two later deaths.
- Immutable skipped bulk-weight audit rows: exactly 90.
- Previously observed immutable SAM review rows containing one or more A523
  identities in `decision_json`: exactly 362.

The later governed transaction must reproduce the exact SAM row-ID manifest,
the exact referenced A523 identity set for each row and the SHA-256 of each
canonical `decision_json` payload. Any count, row, payload, identity,
authority-flag or append-only-guard mismatch aborts before correction metadata.

## Revised reference allowlist

Allowed historical references are restricted to:

1. the exact ninety `bulk_weight_batch_rows` whose status remains `skipped`;
2. exact `sam_live_stock_conversation_review_events.decision_json` snapshots
   when:
   - the base table's update and delete guards are present;
   - both guards are enabled, bound to the exact mutation-blocking function
     and have matching definition fingerprints;
   - every action/authority and owner-review flag is false;
   - recommendation is empty, mode is `READ_ONLY`/`SHADOW`, and source is an
     allowlisted historical snapshot source;
   - the pig identity occurs only in `decision_json`;
   - every pig ID is an exact JSON scalar on a governed inventory-snapshot
     path, never a substring or narrative-text match;
   - the exact review-event ID, JSON path, referenced identity set and payload
     digest are bound into the operation packet.

Any current/action-bearing SAM row, identity outside `decision_json`, weight,
movement, observation, medical, lifecycle, purpose, availability, reservation,
allocation, sale, stock, media, customer mutation or unknown reference remains
a hard transaction blocker.

## Exact governed after-state

- Current Zigay July 2026 litter representations: 1 (`LIT-2026-B1A8`).
- Current child identities for that farrowing: the exact ten B1A8 identities.
- Current live B1A8 piglets: 7.
- Stillborn: 1.
- Later deaths: 2.
- A523 and its ten identities: history/audit only.
- Active/on-farm canonical herd count delta: exactly -9.
- SAM review payload bytes changed: 0.
- Customer records changed: 0.
- Base litter, pig, mating and bulk-audit rows changed: 0.
- Pairwise child merges or reparenting: 0.
- Direct replay rows: 0.
- Whole-operation replay rows: 0.

Current inventory, HERDMASTER, sales and Oom Sakkie readers continue to use
canonical pig/litter projections. Current owner-card, owner-approval and
response-authority consumers use
`current_actionable_sam_live_stock_review_events`, which excludes only exact
review-event IDs committed in the supersession manifest. Explicit historical,
delivery-truth and audit readers retain the immutable base review table.
