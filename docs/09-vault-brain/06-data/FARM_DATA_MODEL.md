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

## One-Pig-Truth Rules

- `PIG_MASTER`/canonical pig table owns identity and lifecycle state.
- Formula/read-model views may explain state, but must not become write targets.
- Weight, location, medical, mating, and litter records should remain event/audit-friendly.
- Pig purpose/allocation must be dynamic and owner-reviewed where it changes operational state.
- Unknown purpose is a classification gap, not a sale/meat/slaughter decision.
- Sale/slaughter/meat exits must link back to explicit order or sales transaction evidence where possible.

## Herdmaster To SAM Sales Availability Read Contract

SAM Live Stock sales must consume the Herdmaster/Pig Allocation derived sales availability read model as authoritative stock context. The read model must carry:

- pig identity, tag, sex, status, on-farm state, purpose, reservation status, and order link;
- latest weight and latest weight date;
- medical withdrawal clearance, current withdrawal end date, and health exclusion reason when a medical hold exists;
- live-stock sale eligibility and explainable block/sale reason;
- sale category, weight band, suggested price category, and pen;
- litter and parent/family context where source records provide it;
- animal media references only when a canonical animal media source exists. If none exists, expose an empty `media_references` list and an explicit source status instead of inventing URLs.

SAM must not offer or prepare order candidates for sold, exited, terminal, off-farm, reserved, breeding/retained, non-`Purpose = Sale`, withdrawal-blocked, or source-conflicted animals. Latest weight date must remain visible wherever SAM sales availability stock cards are shown.

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
