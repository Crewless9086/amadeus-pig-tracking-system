# `/matings` Codex/UI Isolated Implementation Handover

## Start condition

Do not start until HERDMASTER has deployed and owner-visibly proven the corrected contract for:

- authoritative sow/boar names and separate IDs;
- typed active-exposure meaning;
- active-exposure exclusion from placement cohorts;
- Molly's post-litter/nursing precedence; and
- governed body-condition holds for Bonnie, Waki, Zigay and Teena.

Charl must not need to repeat farm facts merely to satisfy this start gate.

## Worktree boundary

Create a new isolated clean worktree from then-current authoritative `origin/main`. Do not build from the shared dirty workspace or reuse an older experimental preview as a base.

Preserve without modification until separately reconciled:

- shared workspace edits to `templates/matings.html` and `static/js/matings.js`;
- untracked mating stylesheets and shared navigation;
- `C:/tmp/matings-dashboard-facelift-20260812`;
- `C:/tmp/matings-facelift-v3-20260812`; and
- all other dirty or unique worktrees.

Inspect those sources read-only for owner-approved intent and unique work, but do not cherry-pick or overwrite them without a lineage/diff reconciliation.

## Required sources

Read the current authoritative versions of:

- `templates/matings.html`;
- `static/js/matings.js`;
- the mating-specific stylesheets;
- `static/css/farmDashboardV2.css`;
- `templates/_farm_nav.html`;
- `AMADEUS_FARM_UI_FACELIFT_STANDARD.md` once it is authoritative and tracked;
- `CHARLIE_CORE_UI_MISSION_STANDARD.md`;
- the consolidated mission contract and regression checklist.

Inspect the live dashboard and at least two approved operational descendants before layout work.

## Data contract consumed

The browser must consume authoritative fields rather than derive identity or lifecycle:

- separate sow/boar names and IDs;
- cycle type/current owner-facing state;
- IN;
- planned UIT;
- actual UIT;
- service-window start/end;
- farrowing-window start/end;
- current pen;
- next-action state and date;
- current hold/recovery meaning.

Unknown exact service, conception and pregnancy remain Unknown.

## Owned UI changes

- Omit the entire active-exposure section when empty.
- Use compact owner language such as `Soe by beer`/approved Afrikaans.
- Show grouped current exposure and one `Teken werklike UIT aan` action.
- Reveal protected preview only after action selection.
- Give window-based and exact-date cycles appropriate card layouts.
- Prefer names; retain IDs only as secondary evidence.
- Make current exposure, placement candidates, recovery holds and history visually distinct.
- Preserve all routes, guarded actions and replay protection.

## Non-owned changes

Do not alter canonical breeding eligibility, identity resolution, thresholds, exposure semantics, farm data or Telegram/voice interpretation. Return contract defects to HERDMASTER rather than masking them in JavaScript.

## Review package

Provide Charl with:

- a faithful local URL;
- an active-exposure example using the real five-cycle shape;
- an empty-state proof where the section is absent;
- Molly nursing and low-condition recovery examples;
- desktop/laptop and mobile visual evidence;
- a concise list of facts displayed and actions preserved.

No deployment before explicit approval.
