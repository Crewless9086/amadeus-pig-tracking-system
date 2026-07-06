# Herdmaster Pig Allocation Alert Rules

Status: draft authority for owner review before implementation.

Purpose: define the source-of-truth rules and implementation design pack for future Herdmaster Pig Allocation alerts. These alerts are advisory, read-only, and owner-gated until a later approved build creates code and tests.

## Source Of Truth

Use these sources in this order:

1. Latest direct owner instruction.
2. Supabase canonical farm records and read models where migrated.
3. Vault Brain rules after owner review.
4. Active `docs/00-start-here/` workflow docs.
5. Existing Pig Allocation readiness code and tests as implementation evidence, not durable business authority.

Primary data sources:

- `pigs` / `PIG_MASTER`: pig identity, tag, sex, status, purpose, on-farm state, litter and parent links, exit fields.
- `pig_current_state` / `PIG_OVERVIEW`: current read model for dashboard and allocation views.
- `pig_weight_events` / latest weight views / `WEIGHT_LOG`: latest weight, weight date, growth evidence, post-wean weight.
- `pig_location_events` / latest location views / `PEN_REGISTER`: current pen and pen metadata.
- `pig_medical_events`: treatment and withdrawal context before sale or meat confidence.
- `litters`: wean date, wean weight, litter quality, sow/boar links, survival context.
- `mating_events`: future sow replacement and breeding context once replacement rules are implemented.
- order, reservation, sales, and slaughter transaction records: existing commitments and exit evidence.

Markdown docs define rules and review boundaries. Runtime data defines live pig state.

## Implementation Boundary

Future alerts should build on the existing read-only Pig Allocation surface:

- route: `/pig-allocation`;
- API: `/api/pig-weights/pig-allocation-readiness`;
- purpose review APIs: `/api/pig-weights/purpose-review`, `/api/pig-weights/purpose-review/apply`, `/api/pig-weights/purpose-review/recheck`;
- implementation files: `modules/pig_weights/pig_weights_service.py`, `templates/pig-allocation.html`, `static/js/pigAllocation.js`;
- focused test file: `tests/test_pig_allocation_readiness_service.py`.

The alert layer must not create a second allocation engine. It should consume or extend the same canonical allocation packet: readiness bucket, reason, latest weight, days since weight, growth class, meat/abattoir timing, litter quality, suggested purpose, suggested-purpose reason, confidence, current links, and source metadata.

No migration is required for the first alert build unless a later mission adds stored alert acknowledgements, owner decisions, or alert history.

## Alert Categories

| Alert | Trigger | Default Severity | Owner Decision Boundary |
| --- | --- | --- | --- |
| Missing Data | Missing tag, sex, weight, pen, identity, wean date/weight where needed, or source conflict blocking trusted classification. | High when allocation is blocked; Medium when useful but not blocking. | Owner may request data correction or capture. No sale, meat, slaughter, or breeding action may proceed from this alert alone. |
| Purpose Review Due | More than 14 days after weaning and post-wean weight exists, or purpose is blank/Unknown with enough basic data to classify. | Medium; High if the pig is also in a sale/meat/slaughter timing window. | Owner approves, overrides, defers, or asks Herdmaster to recheck. Backend writes only through approved purpose-review rails. |
| Meat Window Entered | Latest trusted weight is in the owner window `60-<80 kg`. | High when weight is fresh; Medium when weight is older than fresh-weight rule but not stale. | Owner decides whether to coordinate meat preorder review. No customer promise, reservation, slaughter, or public listing is automatic. |
| Meat Window Expiring / Past | Pig is near the top of the meat window or has reached/passed `80 kg`. | High; Critical only when an approved preorder or owner plan is at risk. | Owner decides whether to push demand, hold, or move to slaughter/abattoir planning. |
| Slaughter Candidate | Latest trusted weight is `80 kg+`, meat window has passed, or owner-approved cull/slaughter context exists. | High. | Owner must approve slaughter/abattoir planning. Alert cannot book slaughter, confirm exit, reserve stock, or mark lifecycle. |
| Slow Grower Feed Risk | Growth class is `Extremely Slow` or `Slow`, especially under `0.200 kg/day`, or a pig is underperforming compared with its age/stage. | Medium; High if feed/capacity pressure or repeated poor growth is visible. | Owner decides whether to keep growing, check health/feed, sell live, or cull through approved rails. |
| Breeding Candidate | Good or exceptional growth plus good litter/sow/boar signal, current purpose says breeding/retention, or Herdmaster review suggests retention before meat/slaughter. | Medium; High for rare strong replacement candidates. | Owner decides retention. Alert cannot create mating plans, change purpose, or remove from sale/meat pool automatically. |
| Stale Weight | Latest weight is older than `30 days` or missing. | Medium; High when the stale weight is being used for value, meat, slaughter, or breeding decisions. | Owner may request weighing. Alert must degrade confidence and block final allocation confidence. |
| Sold/Exited Data Conflict | Pig appears sold, slaughtered, dead, removed, off-farm, or linked to an exit while another read model still shows active/available/on-farm. | Critical. | Owner/admin reconciliation is required. Alert must block allocation, marketing, slaughter, breeding, and customer-facing availability until resolved. |
| Future Sow Replacement | Future alert for replacement planning using sow age/parity, litter outcomes, daughter quality, health, and breeding records once the data contract is approved. | Medium by default. | Owner decides replacement strategy. Alert cannot retire, replace, mate, cull, or reclassify sow/gilt records. |

## Severity Rules

- `Critical`: source conflict, exited/sold inconsistency, or an alert that could cause wrong lifecycle, customer, payment, reservation, or slaughter action if ignored.
- `High`: time-sensitive owner decision, blocked allocation, meat/slaughter timing window, stale data affecting a live business decision, or animal welfare concern.
- `Medium`: normal owner review, classification, slow growth, breeding opportunity, or stale data not yet driving an external promise.
- `Low`: informational watch item with fresh data and no immediate owner action.

Severity must be explainable with source fields and a short reason. If the reason cannot name source data, the alert must be downgraded to draft/advisory or blocked as missing evidence.

## Confidence Rules

- Alert confidence target is 96% before an alert is presented as build-ready or owner-review-ready.
- Pig-level alert confidence must degrade when data is missing, stale, conflicting, fallback-only, or derived from unknown-purpose records.
- `High` confidence requires current canonical source data, no sold/exited conflict, a clear trigger, and no blocked owner decision.
- `Medium` confidence is allowed for advisory review when the source signal is useful but incomplete.
- `Low` confidence must use wording such as `Needs Review`, `Needs Data`, or `Draft Signal`; it must not recommend a final action.
- Unknown purpose is a classification gap, not a sale, meat, slaughter, or breeding approval.
- Stale or missing weight blocks final meat/slaughter/value confidence until a fresh weight or owner-approved override exists.

## Forbidden Actions

Herdmaster alerts must not:

- change pig lifecycle, purpose, death, movement, medical, litter, mating, breeding, weight, slaughter, reservation, payment, order, or customer records;
- create stock reservations, sales transactions, slaughter bookings, delivery promises, customer messages, or public posts;
- treat a missing/Unknown purpose as approval for meat, slaughter, sale, or breeding;
- mark a pig available when sold, exited, terminal, reserved, or source-conflicted;
- suppress stale/missing/conflicting source warnings to make a recommendation look cleaner;
- make future sow replacement alerts into automatic replacement, culling, retirement, or mating decisions.

## Owner Gates

Owner approval is mandatory before:

- applying purpose-review decisions;
- changing lifecycle, purpose, movement, medical, mating, litter, death, exit, slaughter, sale, reservation, order, or payment records;
- sending customer-facing availability, meat, slaughter, pricing, delivery, or timing messages;
- making public posts;
- applying migrations or adding stored alert history;
- using alerts to drive automated farm lifecycle writes.

## First Build Design

The first implementation should:

1. Add an advisory alert packet to Pig Allocation readiness or a small companion read-only service.
2. Compute alerts from the same canonical allocation rows and thresholds already used by Pig Allocation.
3. Return per-alert `category`, `severity`, `confidence`, `reason`, `source_fields`, `owner_action`, `forbidden_actions`, and `pig_id`.
4. Summarize counts by severity and category.
5. Keep UI actions read-only: review, filter, inspect pig, open purpose-review packet.
6. Add focused unit tests for every alert category, stale/conflict downgrades, and no-write flags.
7. Add frontend contract tests only if the alert UI is changed.

## Test And Evidence Expectations

Future builds must record exact commands and results. Minimum focused coverage:

- missing data blocks allocation confidence;
- purpose review due follows the 14-day post-wean rule;
- `60-<80 kg` meat window and `80 kg+` slaughter window boundaries;
- slow growth under `0.200 kg/day`;
- good/excellent grower plus good litter breeding review;
- stale weight over `30 days`;
- sold/exited conflict is Critical and blocks action;
- future sow replacement remains advisory only until data rules are approved;
- no alert path writes to Sheets, Supabase, orders, sales, slaughter, reservations, or lifecycle records.

## Open Design Issues

- Exact meat-window expiring day threshold before `80 kg` needs owner review.
- Exact future sow replacement data contract needs owner review before implementation.
- Whether alert acknowledgements/history should be stored needs a separate owner-approved migration mission.

## Source References

- `docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md`
- `docs/09-vault-brain/00-governance/REVIEW_AND_APPROVAL_RULES.md`
- `docs/09-vault-brain/02-agents/farm/HERDMASTER.md`
- `docs/09-vault-brain/04-workflows/HERDMASTER_PURPOSE_REVIEW_WORKFLOW.md`
- `docs/09-vault-brain/06-data/FARM_DATA_MODEL.md`
- `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md`
- `docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md`
- `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md`
