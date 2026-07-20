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

## Pig Observation Event Contract

`pig_observation_events` is an additive, unapplied canonical fact rail. Each row is tied to one canonical `pig_id`, has an observation and recording timestamp, observer/source provenance, controlled factual category/severity, non-empty factual note, optional object-shaped measurements, and a caller idempotency key.

- Observations are evidence, not diagnoses, treatment instructions, lifecycle/purpose decisions, or external-action instructions.
- Events are append-only. Corrections must be new factual events linked by `supersedes_observation_event_id`; normal updates and deletes are database-blocked.
- A correction can supersede only an earlier observation for the same pig; the observation timestamp cannot be later than its recorded timestamp.
- The table has RLS enabled and no browser policy is introduced by this migration. A future protected backend capture rail must define its own permission and audit contract.
- Herdmaster may consume recent observations only as cited, freshness-aware advisory evidence. It remains read-only and owner-gated; observation presence cannot trigger an automated farm or commercial write.
- Alert acknowledgements, recommendations, owner decisions, automation state, notification delivery, and retention/deletion policy require separately approved data contracts.

## One-Pig-Truth Rules

- `PIG_MASTER`/canonical pig table owns identity and lifecycle state.
- Formula/read-model views may explain state, but must not become write targets.
- Weight, location, medical, mating, and litter records should remain event/audit-friendly.
- Pig purpose/allocation must be dynamic and owner-reviewed where it changes operational state.
- Unknown purpose is a classification gap, not a sale/meat/slaughter decision.
- Sale/slaughter/meat exits must link back to explicit order or sales transaction evidence where possible.

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
