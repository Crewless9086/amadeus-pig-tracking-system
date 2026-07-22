# Farm Data Model

Supabase canonical farm tables/views include pigs, pens, farm products, app settings, weight events, location events, medical events, litters, mating events, latest views, and pig current state where migrated.

Farm record writes require approved backend paths and audit evidence.

## Core Farm Entities

| Entity | Purpose |
| --- | --- |
| Pigs | Stable pig identity, tag, type, sex, status, purpose, on-farm state, parent/litter links, exit fields. |
| Pens | Physical location reference. |
| Weight events | Append-only weight history and growth evidence. |
| Location events | Movement/pen history. |
| Medical events | Treatments, withdrawal dates, sale-safety context. |
| Litters | Birth/weaning/litter outcome records. |
| Mating events | Breeding transaction records and expected outcomes. |
| Pig current/latest views | Read models for dashboard, purpose review, sales availability, and agent summaries. |
| Farm products/settings | Medicine/product defaults and system settings. |
| Pig observation events | Append-only factual human observations for read-only Herdmaster evidence; never a lifecycle, purpose, medical, sales, reservation, slaughter, customer, alert-acknowledgement, or owner-decision store. |
| Pig management intent events | Append-only advisory plans such as `sell_after_weaning`; never a factual observation, approval, action, or current-state write rail. |
| Pig lifecycle events | Append-only audit evidence for canonical pig lifecycle facts; never a lifecycle write rail or substitute for the current-state projection on `pigs`. |
| Riversdale auction cycles | Unapplied owner-confirmation and advisory cohort-snapshot rail. A canonical active-outlet claim rail permits at most one active customer sale, reservation, auction, meat, breeding, health-hold, keep-growing, abattoir, or future outlet state per pig. The migration synchronizes the current protected Supabase order-reservation, sales-transaction, and meat-batch writers transactionally; a conflicting source write fails closed. Future protected cohort execution must create its matching claim and member transactionally. Neither auction rail is a reservation, sale, lifecycle, or customer-send rail. |

## Pig Observation Event Contract

`pig_observation_events` is an additive, unapplied canonical fact rail. Each row is tied to one canonical `pig_id`, has an observation and recording timestamp, observer/source provenance, controlled factual category/severity, non-empty factual note, optional object-shaped measurements, and a caller idempotency key.

- Observations are evidence, not diagnoses, treatment instructions, lifecycle/purpose decisions, or external-action instructions.
- Events are append-only. Corrections must be new factual events linked by `supersedes_observation_event_id`; normal updates and deletes are database-blocked.
- A correction can supersede only an earlier observation for the same pig; the observation timestamp cannot be later than its recorded timestamp.
- The table has RLS enabled with an insert policy limited to the backend `service_role`; no anonymous or authenticated-browser write policy exists. The protected owner-admin backend capture rail derives and persists a stable, non-secret actor reference from the signed authenticated session instead of trusting client-supplied authorship.
- Herdmaster may consume recent observations only as cited, freshness-aware advisory evidence. It remains read-only and owner-gated; observation presence cannot trigger an automated farm or commercial write.
- Alert acknowledgements, recommendations, owner decisions, automation state, notification delivery, and retention/deletion policy require separately approved data contracts.

## Pig Management Intent Event Contract

`pig_management_intent_events` is an additive, unapplied advisory planning rail. Each row is tied to one canonical `pig_id` and records a dated, authored, controlled management intent, rationale, bounded confidence, optional same-pig observation evidence reference, source provenance, and caller idempotency key.

- An intent is distinct from factual observation evidence and is permanently `advisory`; it cannot approve or execute a purpose, lifecycle, sale, reservation, slaughter, customer, notification, or other operational action.
- Events are append-only. Corrections must be new intent events linked by `supersedes_management_intent_event_id`; normal updates and deletes are database-blocked.
- Referenced observation evidence and superseded intents must belong to the same pig. The intended timestamp cannot be later than its recorded timestamp. RLS permits inserts only to the backend `service_role`; no browser write policy exists. The protected owner-admin backend capture rail persists the same server-derived actor reference and records advisory intents without calling an action rail.
- A separate protected, owner-approved action rail may later cite a management intent, but neither creating nor reading an intent may mutate `pigs` or any operational projection.

## Pig Lifecycle Event Contract

`pig_lifecycle_events` is an additive, unapplied audit rail for immutable lifecycle evidence linked to one canonical `pig_id`. Each row has a controlled lifecycle-event type, effective and recorded timestamps, actor and source provenance, an object-shaped payload, a caller idempotency key, and an optional correction link.

- `pigs` remains the canonical mutable current-state projection for lifecycle and exit facts. This rail does not change `pigs`, execute an exit, or change a pig's current state.
- Events are append-only. Only `lifecycle_correction` events may carry `supersedes_lifecycle_event_id`, and every correction must carry one. Updates and deletes are database-blocked, and a correction may supersede only an event for the same pig.
- The effective timestamp cannot be later than the recorded timestamp. RLS is enabled and no browser policy or writer integration is introduced by this migration.
- A future protected lifecycle-write rail must emit this evidence through its approved, owner-gated backend path. Canonical detail/history reads and frontend visibility are separate dependent work.

## Pig Purpose Correction Batch Contract

`pig_purpose_correction_batches` is an additive, unapplied protected batch rail for owner-approved purpose corrections. A batch stores its decision snapshot, decision hash, caller idempotency key, creator, owner-approval identity/time, and execution identity/time. Only a persisted `owner_approved` batch may execute. Execution rechecks the canonical active/on-farm state and latest weight at runtime; missing or stale weight blocks every correction in the batch. Each permitted mutable `pigs.purpose` update and its `operational_events` audit event occur in one transaction, and there is no Google Sheets fallback. Applying the migration remains owner-gated.

## One-Pig-Truth Rules

- `PIG_MASTER`/canonical pig table owns identity and lifecycle state.
- Formula/read-model views may explain state, but must not become write targets.
- Weight, location, medical, mating, and litter records should remain event/audit-friendly.
- Pig purpose/allocation must be dynamic and owner-reviewed where it changes operational state.
- Unknown purpose is a classification gap, not a sale/meat/slaughter decision.

## Read-Only Breeding Match Safety Facts

The current canonical `pig_current_state`/`pigs` read projection does not supply genetics, breeding availability, per-pig reservation clearance, or source-conflict clearance for Herdmaster's breeding matcher. The projection must expose each absent fact as `Unknown`; Herdmaster must fail closed and return no safe-match claim until a separately owner-approved canonical data contract supplies the evidence. This is not a migration authorization and must not be solved with Google Sheets fallback, inferred values, or a farm-record write.
- Sale/slaughter/meat exits must link back to explicit order or sales transaction evidence where possible.
- Riversdale auction recommendations remain advisory until a persisted owner confirmation supplies operating status and a confirmed date. Existing customer orders/reservations, retention, health/withdrawal holds, and lifecycle conflicts exclude a pig from the cohort.

## Litter Detail Read Contract

- Litter detail reads should expose the operational detail state: active, weaned, or completed.
- Active litter summaries may show estimated wean timing and current-weight rollups.
- Weaned or completed litter summaries should close active wean timing, show actual wean date where known, and use wean-weight outcome fields for litter-level average weight.
- Litter detail attention should include the reason and recommended action when the read model flags attention; if no attention reason exists, the UI should not reserve empty attention space.
- Litter attention reconciliation should count sold, slaughtered, disposed, removed, and completed-sale piglet rows as accounted terminal live-born outcomes, not missing piglets. Litter-level stillborn/mummified counts may account for non-live outcomes without requiring separate pig rows when `Total_Born = Born_Alive + Stillborn/Mummified` and live-born piglet history reconciles.

## Agent Use

- Herdmaster may recommend purpose/lifecycle actions.
- SAM and sales agents may read availability, but cannot make pigs available by assertion.
- Butcher may recommend matching/allocation, but cannot book slaughter or reserve stock alone.
- Oom Sakkie summarizes farm truth and routes attention; it must not create shadow data truth.

## Source References

- `docs/03-google-sheets/SHEET_SCHEMA.md`
- `docs/03-google-sheets/FIELD_DEFINITIONS.md`
- `docs/03-google-sheets/FORMULA_LOGIC.md`
- `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`
- `supabase/migrations/202607200001_create_pig_observation_events.sql` (unapplied; application requires explicit owner approval)
- `supabase/migrations/202607220001_complete_pig_observation_and_management_intent_events.sql` (unapplied; application requires explicit owner approval)
- `supabase/migrations/202607210001_create_pig_lifecycle_events.sql` (unapplied; application requires explicit owner approval)
