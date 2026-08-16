# Amadeus Farm UI Facelift Standard

## Purpose

This is the authoritative product-design contract when Charl asks for a page to receive a **facelift**, to **match the dashboard**, or to use the **same style** as the approved Amadeus Farm pages.

A facelift is not a palette swap. It is a workflow-led redesign that makes the page easier to understand and use while preserving canonical farm data, safety boundaries and guarded actions.

## Governance and worktree preflight

Before implementation, the target terminal must report its exact source HEAD, this file's Git blob, and confirmation that it read the complete tracked file in its own implementation worktree. If this file is absent, untracked or differs from authoritative main, implementation stops for governance reconciliation.

The terminal must also report the dashboard reference revision, confirm that it inspected the shared stylesheet and navigation, and name at least two approved comparison routes inspected from the same authoritative lineage.

## Gold-standard implementation

The approved foundation is the live Amadeus Farm dashboard and its approved descendant pages:

- `static/css/farmDashboardV2.css` supplies shared tokens, shell, navigation and reusable farm components;
- `templates/_farm_nav.html` supplies the persistent top menu;
- `farm-app-shell` is the outer shell;
- `farm-home` is used for the dashboard and `operations-page` for operational/detail pages;
- each route may add one workflow-specific stylesheet.

Approved reference routes include `/`, `/pig/<pig_id>`, `/bulk-weights`, `/print-sheets`, `/api/pig-weights/breeding-attention/view`, `/litters`, and the approved open/closed litter views.

Before building, inspect the current authoritative dashboard, shared stylesheet, shared navigation and at least two approved pages closest to the target workflow. Never reconstruct the foundation from memory or an older worktree.

## Visual foundation

- canvas `#f2f0e8`;
- warm paper `#fffdf8`;
- ink `#20362b` and muted copy `#66766d`;
- structural line `#d8dfd8`;
- farm green `#315f45` and soft green `#e4eee5`;
- restrained operational accents for weather, water, alerts, herd, breeding and sales;
- shared serif display headings and compact sans-serif operational text;
- rounded, bordered, lightly shadowed cards;
- whitespace that separates decisions without wasting space.

The top menu must remain visually and structurally consistent. Route-specific navigation belongs inside the page only when it assists the current job.

## Required page contract

Before layout work, answer:

1. What is the primary farm job?
2. What must Charl, his father or his mother understand at a glance?
3. What is the next useful action?
4. Which captured facts support it?
5. Which historical or technical details should be secondary?
6. What are the loaded, empty, stale, blocked, error and completed states?
7. Which actions are guarded, preview-only or read-only?

The screen should provide shared navigation, clear identity and purpose, a useful current-state summary, a workflow-oriented primary workspace, visible plain-language actions, secondary technical evidence, explicit system states and responsive behavior.

Do not add tiles merely to fill space. Every tile must answer a real owner question and, where useful, open or filter its detailed operation.

## Human identity hierarchy

Owner-facing animal identity is name first, tag second and canonical Pig ID only as muted technical evidence. If neither name nor tag is available, show `Naam/Tag onbekend` and retain the Pig ID as secondary evidence. Internal IDs must not be primary labels except on an explicitly technical reconciliation screen.

Relationship rows must use resolved human identities. Interactive rows must be visibly actionable, keyboard accessible and screen-reader usable. Drill-down routes must validate any internal `return_to` value and show a clear contextual Afrikaans return label.

## Data and workflow rules

- Use real data already captured by the application.
- Preserve existing routes unless a separately approved functional change is required.
- Do not invent facts, calculations, stages or sources to make a page look complete.
- Use consistent farm language and owner-approved Afrikaans terminology.
- Prefer names and human-readable states; keep IDs secondary.
- Show one clear meaning per status; avoid repetitive generic cards.
- Design around actual farm work, not database table shapes.
- Do not create a competing interpretation or mutation path for browser, Telegram or voice actions.

## Required build sequence

1. Verify authoritative lineage and governance.
2. Inspect the live target and approved reference routes.
3. Inspect authoritative `farmDashboardV2.css` and `_farm_nav.html`.
4. Map route data, actions, users and workflow.
5. Write a page-specific hierarchy, action, state and responsive contract.
6. Build in an isolated clean worktree from current authoritative main.
7. Preserve functionality and guards.
8. Render representative real or faithful read-only data.
9. Compare desktop/laptop and mobile views with approved references.
10. Give Charl a real local preview and wait for explicit approval before merge or deployment.

## Structural and preview-health gates

Automated route checks for a facelift must verify use of `farmDashboardV2.css`, `_farm_nav.html`, `farm-app-shell` and `operations-page`. A deliberate departure requires a documented, independently reviewed exemption tied to the exact route and source revision.

Before a local URL is presented to Charl, the preview runner must prove:

- the page and required CSS/JavaScript assets load successfully;
- the primary data API succeeds under an authenticated owner session or a clearly labelled faithful read-only fixture;
- representative content renders rather than an empty skeleton or endless loading state;
- primary actions, keyboard navigation and contextual return journeys work;
- desktop and approximately 390px mobile journeys have no clipping or horizontal page overflow;
- loading, empty, unavailable, stale, error and completed states are explicit.

An HTML `200` with an API authentication failure is a failed preview, not owner-review evidence.

## Owner approval deployment lock

Every owner-facing UI change stops at `READY_FOR_OWNER_PREVIEW`. The review packet must identify the exact preview URL, source commit, desktop and mobile evidence, data or fixture source, and routes tested.

Merge and deployment are prohibited until Charl explicitly approves that exact preview and exact source revision. Any source change after approval invalidates the approval and requires a fresh preview. CI, automated tests, screenshots and independent reviewers support owner approval; they never replace it.

## Acceptance gate

A facelift is not review-ready unless shared assets load, the page visibly belongs to the approved product family, the primary workflow is simpler, real data/actions are correctly placed, nothing clips or overflows, degraded states are clear, desktop and mobile evidence exists, and the preview comes from the implementation lineage under review.

If shared assets are absent, stop and reconcile current lineage. Never substitute an improvised visual system.

## Current rollout

Pages are upgraded one at a time. Existing missions retain their identities and must reconcile to this standard rather than creating duplicate UI missions.
