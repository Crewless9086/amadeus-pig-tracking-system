# Pig Lifecycle Outcome Plan

## Purpose

Phase 9.7 makes animal outcomes auditable and useful for reporting. The system should record what happened to each pig once, through backend-owned actions, then let pig, litter, sow, boar, sales, slaughter, and dashboard views derive from that truth.

This is not an automated recommendation engine. It is the data-quality layer needed before recommendations can be trusted.

## Current State Audit - 2026-06-01

| Outcome | Current write path | Current source of truth | Reporting today | Gap |
| --- | --- | --- | --- | --- |
| Born alive piglets | `save_new_litter()` creates `PIG_MASTER` piglet rows from `LITTERS.Born_Alive` | `LITTERS`, `PIG_MASTER` | `LITTER_OVERVIEW` compares live pig records to born-alive count | Good baseline; still needs lifecycle event history later. |
| Stillborn / mummified | Litter form/source records counts only | `LITTERS` | `LITTER_OVERVIEW` treats these as litter outcome metrics, not pig rows | Good rule; must preserve during future migration. |
| Weaning | `POST /api/pig-weights/litter/<litter_id>/mark-weaned` calls `mark_litter_weaned()` | `LITTERS.Wean_Date`, `LITTERS.Weaned_Count`, linked `PIG_MASTER.Wean_Date` / `Litter_Size_Weaned` | Litter attention and breeding analytics can read weaning outcome | Backend action exists. It does not yet log a separate lifecycle event. |
| Live-stock sale / order completion | `POST /api/orders/<order_id>/complete` calls `complete_order()` | `ORDER_MASTER`, `ORDER_LINES`, `PIG_MASTER` | Dashboard can count monthly livestock exits from `PIG_MASTER.Exit_Date` / `Exit_Reason`; orders show completed state | Backend action exists for order-based sales. Needs a clean link to future sales transaction reporting. |
| Slaughter / abattoir sale transaction | `/sales/slaughter` writes Supabase `sales_transactions` and `sales_transaction_items` | Supabase sales transaction tables | Dashboard Rand/count cards read Supabase sales transactions | Intentionally does not update `PIG_MASTER` yet. Pig/litter/breeding outcome views can therefore miss slaughter exits unless `PIG_MASTER` is manually updated. |
| Slaughter pig state | Manual/current sheet correction only, when done | `PIG_MASTER.Status`, `On_Farm`, `Exit_Date`, `Exit_Reason`, `Carcass_Weight_Kg` | Dashboard pig-exit audit counts read `PIG_MASTER` | Needs backend-owned confirmation/linking action. |
| Death / removal | No complete backend-owned action found | Likely manual `PIG_MASTER` update using `Status`, `On_Farm`, `Exit_Date`, `Exit_Reason`, notes | Litter overview can count non-active linked pig rows as exited, but reason-specific death reporting is not explicit | First real gap. Needs controlled action before outcome reporting can be trusted. |
| Meat stream movement | Future business module | Not yet a stable source | Dashboard has a future stream placeholder via Supabase transaction summary and pig exit reason mapping | Park until slaughter/meat business flow is clearer. |

## Existing Field Anchors

`PIG_MASTER` already has the minimum state fields needed for the first lifecycle actions:

- `Status`
- `On_Farm`
- `Current_Pen_ID`
- `Litter_ID`
- `Litter_Size_Born`
- `Litter_Size_Weaned`
- `Wean_Date`
- `Wean_Weight_Kg`
- `Exit_Date`
- `Exit_Reason`
- `Exit_Order_ID`
- `Carcass_Weight_Kg`
- `General_Notes`
- `Updated_At`

`LITTER_OVERVIEW` already depends on linked `PIG_MASTER` rows for:

- `Pig_Master_Row_Count`
- `Active_Pig_Count`
- `On_Farm_Pig_Count`
- `Exited_Pig_Count`
- `Litter_Status`
- `Needs_Attention`
- `Attention_Reason`

The important rule is preserved in current docs: piglets that die after live birth must keep their `PIG_MASTER` row because they count toward born-alive survival history.

## Action Matrix

| Action | First route shape | Required inputs | Writes | Readback/reporting impact | Notes |
| --- | --- | --- | --- | --- | --- |
| Mark pig dead/removed | `POST /api/pig-weights/pig/<pig_id>/lifecycle/death` or `/remove` | `event_date`, `reason`, `changed_by`, optional `notes`, optional `category` | `PIG_MASTER.Status`, `On_Farm`, `Exit_Date`, `Exit_Reason`, `General_Notes`, `Updated_At`; future event log | Pig profile, litter outcome, dashboard death/removal counts, breeding survival history | Recommended first build slice. Must preserve row and parent/litter links. |
| Confirm slaughter exit from sale | `POST /api/sales-transactions/<sale_id>/confirm-pig-exits` | `changed_by`, optional `exit_date`, optional notes | `PIG_MASTER` for each linked pig, maybe carcass weight from item rows | Pig/litter/breeding outcomes align with Supabase sale truth | Should be explicit first, not automatic on payment, until owner trusts the flow. |
| Complete order sale | Existing `POST /api/orders/<order_id>/complete` | `changed_by` | Existing order, line, pig updates | Existing dashboard pig-exit counts | Keep as is; later link completed orders to sales transaction rows if needed. |
| Mark litter weaned | Existing `POST /api/pig-weights/litter/<litter_id>/mark-weaned` | `wean_date`, optional `changed_by` | Existing litter and pig wean fields | Litter attention clears; breeding analytics has weaned counts | Keep as is; later add lifecycle event log if useful. |
| Move to meat stream | Future route after meat module is defined | TBD | TBD | Meat inventory and sales reporting | Do not build before Phase 11 shape is clearer. |

## Recommended Next Build: 9.7B Death/Removal Action

Start with death/removal because it is the largest missing backend-owned lifecycle action and affects survival reporting directly.

Minimum backend behavior:

- Validate pig exists.
- Block action when pig is already off-farm/terminal unless an explicit future correction mode is built.
- Accept `event_date`, `reason`, `changed_by`, optional `notes`.
- Set `Status` to `Dead` or `Removed` based on approved reason/category.
- Set `On_Farm = No`.
- Set `Exit_Date` to the event date.
- Set `Exit_Reason` to a normalized reason such as `Died`, `Culled`, `Lost`, `Removed`, or `Other`.
- Append a concise note to `General_Notes` without deleting existing notes.
- Set `Updated_At`.
- Return before/after summary for the UI.

Recommended first UI:

- Add a controlled action on the pig detail page, visible for active/on-farm pigs.
- The form should ask for date, reason/category, changed by, and notes.
- It should clearly warn that the pig row is kept for history and reporting.

Tests to add:

- service validates required fields and dates
- action updates only the selected pig row
- pre-weaning death keeps the litter link intact
- already off-farm/terminal pig is blocked
- route returns safe validation errors
- frontend contract verifies the pig detail page calls the backend action and does not delete records

## Open Decisions

- Exact allowed death/removal categories: suggested first set is `Died`, `Culled`, `Lost`, `Removed`, `Other`.
- Whether `Status` should use `Dead` for all death/cull cases and `Removed` only for non-death removals, or whether `Culled` should be its own status.
- Whether to add a dedicated `PIG_LIFECYCLE_LOG` sheet now, or start with `PIG_MASTER` fields and notes until the action is proven.
- Whether slaughter exit confirmation should happen when the slaughter transaction is created, when it is completed/paid, or through a separate explicit operator confirmation.

## 9.7B Local Implementation State - 2026-06-01

- Added backend service `mark_pig_death_or_removal()`.
- Added route `POST /api/pig-weights/pig/<pig_id>/lifecycle/death`.
- Added a controlled `Lifecycle Outcome` form to `/pig/<pig_id>`.
- The form only appears for pigs whose loaded profile is `Status = Active` and `On_Farm = Yes`.
- Supported first reasons: `Died`, `Culled`, `Lost`, `Removed`, and `Other`.
- `Died`, `Culled`, and `Lost` set `PIG_MASTER.Status = Dead`.
- `Removed` and `Other` set `PIG_MASTER.Status = Removed`.
- All successful actions set `On_Farm = No`, `Exit_Date`, `Exit_Reason`, append to `General_Notes`, and update `Updated_At`.
- The pig row, `Pig_ID`, parent fields, and `Litter_ID` are preserved for litter and breeding history.
- Already terminal/off-farm pigs are blocked; historical correction remains a future separate workflow.
- Local verification passed: `node --check static/js/pigDetail.js`, focused pig lifecycle/frontend tests at 27 tests, route smoke for the pig detail page and invalid lifecycle payload, and full local unittest suite at 316 tests.
- Next step: deploy and browser-check on a non-critical/known test case before using it for an actual farm death/removal record.
