# UI Facelift Tower Register — 2026-08-19

Status: current-state delivery register, not doctrine.

Authority revision: `783a290f8f2478fb74bef6aa089d98a645e73fc0`

Controlling standards:

- `docs/09-vault-brain/07-standards/AMADEUS_FARM_UI_FACELIFT_STANDARD.md`
- `docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md`
- `docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md`

## Operating rule

One Spark UI slice may be active at a time. A slice stops at
`READY_FOR_OWNER_PREVIEW` only after its actual route, shared assets, primary
data state, desktop view, approximately 390px mobile view, keyboard journey,
loaded/empty/error states and no-overflow checks pass.

Spark may change presentation code only. It must not change Vault doctrine,
business rules, database schema, API meaning, authorization, payments, animal
state, customer communication, hardware behavior or production deployment.

No slice may merge or deploy before Charl approves the exact preview and source
revision. Preparing a later isolated preview does not approve an earlier one.

## Inventory basis

The structural inventory inspected all 54 page templates on authoritative main.
It checked for the shared `farmDashboardV2.css`, `_farm_nav.html`,
`farm-app-shell`, and `operations-page`/`farm-home` foundation. Structural
markers are an inventory signal, not visual acceptance; every listed route still
requires real browser inspection.

### Adopted foundation — 9

- `dashboard.html`
- `add-order.html`
- `breeding-attention.html`
- `bulk-weights.html`
- `irrigation.html`
- `litter-detail.html`
- `power.html`
- `print-sheets.html`
- `weather.html`

### Partial foundation — 4

- `add-litter.html`
- `litters.html`
- `matings.html`
- `pig-detail.html`

`litters.html` and `pig-detail.html` are named approved comparison routes in the
facelift standard. Their marker result therefore requires visual confirmation,
not an assumption that they need redesign.

### Foundation not yet adopted — 41

- `add-mating.html`
- `add-pen.html`
- `add-pig.html`
- `add-product.html`
- `beacon-media.html`
- `breeding-analytics.html`
- `breeding-analytics-detail.html`
- `charlie.html`
- `charlie-agents.html`
- `charlie-v2.html`
- `family-tree.html`
- `index.html`
- `meat-driver.html`
- `meat-planning.html`
- `meat-production.html`
- `meat-sales-leads.html`
- `meat-sales-reference.html`
- `oom-sakkie.html`
- `order-detail.html`
- `orders.html`
- `owner-login.html`
- `paring-werpselrekord.html`
- `pig-allocation.html`
- `pig-list.html`
- `pig-movement.html`
- `pig-movement-history.html`
- `pig-treatment.html`
- `pig-treatment-history.html`
- `pig-weight-history.html`
- `pig-weights.html`
- `purpose-review.html`
- `rootline-policy-review.html`
- `sales-availability.html`
- `sales-dashboard.html`
- `sam-live-stock-availability.html`
- `sam-owner-inbox.html`
- `sam-pricing.html`
- `slaughter-sale.html`
- `slaughter-sale-detail.html`
- `verwagte-jongdatums.html`
- `weight-report.html`

`index.html` has no currently discovered `render_template` call and is an
archive/removal candidate, not an automatic facelift target. `owner-login.html`
is an authentication surface and requires a separate security-preserving slice.

## Serialized delivery queue

| Order | Slice | Templates | State |
|---:|---|---|---|
| 0 | Browser inventory and route verification | all 54 | IN PROGRESS |
| 1 | Herd register | `pig-list.html` | ELIGIBLE AFTER INVENTORY |
| 2 | Pig activity | `pig-weights.html`, `pig-weight-history.html`, `weight-report.html` | QUEUED |
| 3 | Pig care | `pig-treatment.html`, `pig-treatment-history.html`, `pig-movement.html`, `pig-movement-history.html` | QUEUED |
| 4 | Herd setup | `add-pig.html`, `add-pen.html` | QUEUED |
| 5 | Breeding operations | `add-mating.html`, `breeding-analytics.html`, `breeding-analytics-detail.html`, `family-tree.html`, `paring-werpselrekord.html`, `verwagte-jongdatums.html` | QUEUED |
| 6 | Existing partial-route reconciliation | `matings.html`, `add-litter.html`; visually verify `litters.html`, `pig-detail.html` | QUEUED |
| 7 | Orders | `orders.html`, `order-detail.html`, `add-product.html` | QUEUED — business behavior frozen |
| 8 | Sales operations | `sales-availability.html`, `sales-dashboard.html`, `slaughter-sale.html`, `slaughter-sale-detail.html` | QUEUED — payment behavior frozen |
| 9 | SAM operations | `sam-pricing.html`, `sam-live-stock-availability.html`, `sam-owner-inbox.html` | QUEUED — customer/provider behavior frozen |
| 10 | Herd planning | `pig-allocation.html`, `purpose-review.html` | QUEUED — advisory semantics frozen |
| 11 | Meat operations | `meat-driver.html`, `meat-planning.html`, `meat-production.html`, `meat-sales-leads.html`, `meat-sales-reference.html` | QUEUED |
| 12 | BEACON media | `beacon-media.html` | QUEUED — publication rules frozen |
| 13 | Oom Sakkie command room | `oom-sakkie.html` | HELD — shared-attention implementation collision |
| 14 | CHARLIE interfaces | `charlie.html`, `charlie-v2.html`, `charlie-agents.html` | HELD — CORE mission/UI-council dependency |
| 15 | ROOTLINE policy review | `rootline-policy-review.html` | HELD — protected-operation semantics |
| 16 | Authentication surface | `owner-login.html` | HELD — security-specific review |
| 17 | Unused-template disposition | `index.html` | VERIFY THEN RETAIN/ARCHIVE/DELETE SEPARATELY |

## Per-slice handover

Each slice must leave a compact packet containing:

- exact source revision and changed files;
- primary farm job and preserved actions;
- reference routes inspected;
- local preview URL and faithful data source;
- desktop and mobile screenshots;
- loaded, empty, stale/unavailable, error and completed-state evidence;
- keyboard/action and overflow results;
- focused test results;
- explicit confirmation of zero backend/business/data/deployment changes;
- state `READY_FOR_OWNER_PREVIEW`, `SEND_BACK`, or `BLOCKED`.

