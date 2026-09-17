# Operational Fixes Master Plan

## Status

- Planning only.
- No code implemented.
- No migrations approved.
- No UI rewrites approved.
- OP-1.1 owner decisions are incorporated.
- No operational ticket is build-ready unless it passes the 96% build confidence gate.

## Source Notes

- `planning/ToDoList.md`
- `planning/inbox/processed/2026-06/ToDoList_2026-06-28_operational_notes.md`

## Build Rules

- Operational fixes come before future builds.
- No CHARLIE, FRED, or Agent Collaboration Ledger SQL work until operational blockers are addressed.
- Phase 3A.6 comes after the operational blockers.
- Use one clean branch/worktree per build package.
- PR required for backend, auth, data, migration, and routing changes.
- Small frontend-only layout fixes may be direct only if explicitly owner-approved, but default is PR.
- Never use `git add .`.
- Do not commit `.env`, screenshots, `external_sources`, `test-results`, `.claude`, or `static/assets` unless specifically approved.
- Supabase is operational truth for new durable rails.
- Google Sheets may remain transitional, but it must not cause silent partial writes.
- Owner approval gates remain for sends, stock changes, money, public posts, reservations, and customer commitments.

## 96% Build Confidence Gate

A ticket cannot be implemented until confidence is 96% or higher, owner decisions are captured, affected files/routes are identified, source-of-truth is confirmed, tests and pressure tests are defined, rollback exists, forbidden actions are listed, the build package is scoped, and there is no unresolved dependency unless explicitly accepted.

If confidence remains below 96%, do not build. List exact missing evidence, exact owner question, and exact test needed.

## Pressure-Test Requirement

Every implemented operational build must include a pressure-test report before merge: normal path, edge cases, duplicate/retry behavior, partial failure behavior, stale/missing data behavior, permission/access behavior, UI degradation behavior, no unsafe action proof, rollback proof, and Render/live verification plan where relevant.

Bulk weights must include the 71-row scenario. Lead qualification must include one-word messages, vague messages, duplicate chats, real buying intent, and auto-follow-up gating. Stock/valuation must include stale weights, no weight, reserved animals, heavy cull animals, and boundary weights.

## Evidence Gathered In OP-1.1

- `/` is the main dashboard route and renders `dashboard.html`.
- `owner_logout_post()` clears the owner session and currently redirects to `owner_login_page`.
- `/sales/meat-leads` is owner-protected when `OWNER_ACCESS_ENABLED=true`.
- `/api/sales/meat-pilot-readiness` calls `get_meat_pilot_readiness()`.
- Pilot readiness reads sales leads, then per lead reads preorder contract, estimated quote packet, meat ops status, and template pack readiness.
- Pilot readiness has no per-lead degraded-source exception isolation around contract/quote/ops reads, so one source exception can plausibly produce the observed 500.
- SAM/Chatwoot intake routes call `record_sam_meat_intake_lead()`.
- `record_sam_meat_intake_lead()` currently blocks only missing customer name as a core field and treats other facts as missing-before-money-path.
- Current SAM meat intake does not enforce the owner-approved real-lead minimum of product intent plus actionable sales fact.
- Bulk weight save uses preflight, row-by-row weight/movement writes, `failed_rows`, `blocked_rows`, `BULK_WEIGHT_BATCH_LOG`, and `BULK_WEIGHT_BATCH_ROWS`.
- Bulk weight UI displays saved, movement, duplicate, skipped, blocked, failed, and audit warning counts, but the 71-row partial-write scenario is not pressure-tested.
- Meat planning thresholds currently come from `DEFAULT_ALLOCATION_SETTINGS`: meat 55-70kg and slaughter/abattoir 80-95kg.
- Current readiness logic treats 120kg as past abattoir window; owner decision is 80kg+ should remain included for cull/heavy slaughter review.
- `/sales-dashboard` reads `SALES_STOCK_SUMMARY` and `SALES_STOCK_TOTALS` through `get_sales_dashboard_data()`.
- Meat pricing uses `list_meat_price_book_entries()` with Supabase-backed rows when configured and `DEFAULT_MEAT_PRICE_BOOK` fallback.

Existing tests run in OP-1.1 all passed:

- `tests.test_owner_access`: 23 tests.
- `tests.test_sales_transaction_routes`: 62 tests.
- `tests.test_pig_weights_bulk_service`: 8 tests.
- `tests.test_pig_allocation_readiness_service tests.test_meat_price_book`: 13 tests.

The clean worktree did not have its own `.\venv\Scripts\python.exe`, so tests were run from the OP-1 worktree using `..\amadeus-pig-tracking-system\venv\Scripts\python.exe`.

## OP-001 Meat Lead Creation And Qualification

- Owner problem statement: one-word chats such as Sinethemba, Pappa G, Thando, `Hi`, `price`, or `yes` appear to become meat leads.
- Owner decision captured: SAM should not create or surface a real meat lead unless minimum facts are clear. Weak chats become conversation events, intake candidates, auto-qualification tasks, or draft follow-up work, not actionable leads.
- Routes/files identified: `/sales/meat-leads`, `/api/sales/meat-leads`, `/api/oom-sakkie/channels/chatwoot/sam-meat-intake`, `/api/sales/channels/chatwoot/sam-meat/inbound`; `modules/oom_sakkie/routes.py`, `modules/oom_sakkie/sales_campaign_store.py`, `modules/sales/sam_meat_runtime.py`, `modules/sales/sales_transaction_routes.py`, route/service tests.
- Source-of-truth confirmed: Supabase-backed sales lead rows/events through existing SAM/Oom Sakkie sales lead rails.
- Evidence: `record_sam_meat_intake_lead()` requires only `customer_name` as a core field and records product/location/timing/payment gaps as missing-before-money-path. This is too broad for the new real-lead rule.
- Real lead minimum facts: identifiable contact/conversation id; product intent such as meat, pork, carcass, cuts, pig, live pig, abattoir, or similar; at least one actionable sales fact such as quantity, cut/product type, location/delivery area, timing/date, price question with product context, or explicit buying intent; enough message content to distinguish buying intent from greeting/noise.
- Required classifications: `raw_conversation_event`, `intake_candidate`, `needs_auto_qualification`, `qualified_meat_lead`, `disqualified_or_noise`, `waiting_customer_reply`.
- Sinethemba/Pappa G/Thando under the new rule: if name/greeting/one word only, classify as `raw_conversation_event` or `intake_candidate`; if contact exists but product/actionable fact is missing, classify as `needs_auto_qualification`; do not show as `qualified_meat_lead` in SAM Command Room.
- Automatic follow-up direction: SAM may gather missing facts only through existing Chatwoot/WhatsApp, opt-in, template, 24-hour window, env flag, approval hash, and Gatekeeper rails. If automated send is not safe, create a draft/follow-up task instead.
- When a lead appears in SAM Command Room: only after `qualified_meat_lead`, or in a clearly separate intake lane if approved later.
- Duplicate prevention: use conversation id/contact id plus normalized recent intent to update the same intake candidate instead of creating repeated leads.
- What not to do: do not delete history, auto-send customers, create orders/reservations, hide raw Chatwoot evidence, or bypass customer-send gates.
- Risk level: high.
- Confidence score: 95%.
- Missing evidence: one live/example payload for the named chats, or a targeted failing test proving the current path turns one-word messages into surfaced command-room leads.
- Exact test needed: inbound `Hi`, `price`, `yes`, and name-only payloads must not create/surface `qualified_meat_lead`; vague product message becomes `needs_auto_qualification`; real buying message with product context and actionable fact becomes `qualified_meat_lead`.
- Implementation phase/batch: OP-BUILD-3.
- Allowed files later: identified route/service files plus focused tests.
- Forbidden files: migrations unless separately approved, send/payment/reservation/public-post routes except read-only checks, CHARLIE/FRED/ledger files.
- Data/migration impact: likely none if existing status/source/interest fields can hold classification; migration only if durable classification field is required.
- Test plan: one-word/no-product inbound chats become unqualified; explicit meat-interest chats become qualified; duplicates update same candidate; no send/order/reservation side effects.
- Pressure-test plan: one-word messages, greetings, vague messages, duplicate chats, real buying intent, contact-only messages, product-only messages, and auto-follow-up send-gate blocked/allowed cases.
- Acceptance criteria: owner can see why a chat is or is not a meat lead; one-word chats do not enter the primary actionable SAM lead workflow.
- Rollback plan: restore previous qualification thresholds/display filter.

## OP-002 Bulk Weight Reliability And Audit Trail

- Owner problem statement: bulk weight add did not save all weights or movements; only 60 entries were added when 71 were expected; there was no clear log/trail.
- Owner decision captured: weekly farm records depend on this; silent partial writes are unacceptable; if Google Sheets is structurally unreliable, propose Supabase-first durable rail without breaking existing Sheets-dependent pages.
- Routes/files identified: `/bulk-weights`, `/api/pig-weights/weights-batch/preflight`, `/api/pig-weights/weights-batch`; `modules/pig_weights/pig_weights_service.py`, controller/routes, `static/js/bulkWeights.js`, `services/google_sheets_service.py`, `tests/test_pig_weights_bulk_service.py`.
- Source-of-truth confirmed: Google Sheets weight and movement logs, with batch/row audit hooks for `BULK_WEIGHT_BATCH_LOG` and `BULK_WEIGHT_BATCH_ROWS`.
- Evidence: implementation writes accepted rows one by one and records `failed_rows`, `blocked_rows`, `movement_rows`, `saved_rows`, duplicate counts, and audit warnings. Existing tests cover duplicate-weight movement, movement-only rows, blocked duplicates, and basic save path.
- Required reliability model: bulk operation id; expected row count; processed row count; success count; failed row count; skipped/duplicate count; per-row result trail; retry-safe/idempotent behavior; clear UI success/failure summary; no silent partial success; exportable audit details; rollback/retry plan.
- Proposed solution direction: short-term Sheets hardening if batching, retries, and audit trail are reliable enough; otherwise Supabase-first durable batch ledger/write queue with optional Sheets sync/read compatibility.
- What not to do: do not remove duplicate protection, bypass preflight, silently retry without idempotency, or migrate write rails without explicit approval.
- Risk level: high.
- Confidence score: 95%.
- Missing evidence: 71-row reproduction/pressure test or live audit evidence for the June 15 run; timing/failure behavior from Google Sheets append helper under partial failure.
- Exact test needed: 71 valid rows, simulated timeout after 60 writes, retry same operation id, duplicate rows, partial failure, movement creation for every successful weight, and visible audit trail.
- Implementation phase/batch: OP-BUILD-2.
- Allowed files later: identified bulk weight files plus focused tests.
- Forbidden files: unrelated pig modules, migrations unless separately approved.
- Data/migration impact: none for audit UI/reporting; possible future Supabase batch ledger migration.
- Pressure-test plan: reproduce the 71-row upload, force save failure at row 60, verify submitted/processed/saved/moved/skipped/failed counts, verify no silent success, verify retry outcome.
- Acceptance criteria: owner sees submitted, saved, moved, skipped, blocked, and failed counts; every row has a trace; partial writes are visible.
- Rollback plan: retain existing batch save behavior and disable only new audit display/reporting.
- Owner decision still needed: approve Sheets hardening first or Supabase-backed durable rail if pressure test proves Sheets is structurally unreliable.

## OP-003 Meat Planning Weight Window Settings

- Owner problem statement: `/meat-planning` shows meat and abattoir windows, but owner cannot edit them; desired defaults are 60-80kg meat and 80kg+ abattoir/cull.
- Owner decision captured: 80kg+ includes heavy breeding sows/culls such as 120kg animals when they need slaughter review.
- Routes/files identified: `/meat-planning`, `/api/pig-weights/meat-planning`, `/api/pig-weights/pig-allocation-readiness`; `modules/pig_weights/pig_weights_service.py`, routes, `static/js/meatPlanning.js`, `templates/meat-planning.html`, `tests/test_pig_allocation_readiness_service.py`.
- Source-of-truth confirmed: code defaults in `DEFAULT_ALLOCATION_SETTINGS`: meat 55-70kg, slaughter/abattoir 80-95kg.
- Evidence: current readiness logic has an upper slaughter max and treats 120kg as `Past abattoir window`; owner wants 80kg+ included for cull/heavy review.
- Proposed source-of-truth: short-term code defaults with explicit display; later owner-editable settings should use a guarded durable settings source, preferably Supabase-backed when migration is separately approved, with code defaults fallback.
- What not to do: do not add public write controls, change SAM stock promises, or create settings persistence without approval.
- Risk level: medium.
- Confidence score: 96%.
- Missing evidence: none for planning; implementation still needs file-scoped approval.
- Implementation phase/batch: OP-BUILD-4.
- Allowed files later: pig allocation/meat planning service, route, template, JS, focused tests.
- Forbidden files: migrations unless settings storage is approved, SAM send/payment/reservation code.
- Data/migration impact: none for default/label update; possible settings table/config later.
- Test plan: 59.9kg not meat-window, 60kg meat-window, 80kg boundary included in abattoir/cull logic, 120kg abattoir/cull candidate, labels show source/defaults.
- Pressure-test plan: boundary weights, missing weights, stale weights, breeding/cull status, reserved/sold/excluded status, and changed settings preview.
- Acceptance criteria: owner can view active meat/abattoir windows and later update them safely if settings page is approved.
- Rollback plan: restore previous code defaults and disable settings override.

## OP-004 Pig Allocation Purpose Review Workflow

- Owner decision captured: owner wants to dig deeper, review recommendations, and assign/confirm pig purpose later; no build yet; P3 until bulk weights and stock readiness are stable.
- Routes/files identified: `/pig-allocation`, `/purpose-review`, `/api/pig-weights/pig-allocation-readiness`, `/api/pig-weights/purpose-review`; allocation/purpose templates, JS, service/routes.
- Source-of-truth confirmed: Google Sheets pig overview/master data with purpose-review decisions through existing service.
- Evidence: route contract tests confirm allocation, purpose review apply/recheck, and allocation readiness surfaces exist.
- Proposed direction: inspect recommendation -> open pig detail -> recheck -> preview selected decision -> apply selected purpose through existing rails.
- What not to do: no automatic bulk purpose changes, no reclassification without explicit flow, no bypass of dry-run/owner preview.
- Risk level: medium.
- Confidence score: 94%.
- Missing evidence: live page workflow inspection and owner decision on one-page workflow vs allocation-to-purpose-review handoff.
- Implementation phase/batch: OP-BUILD-5.
- Allowed files later: allocation/purpose templates, JS, `static/css/main.css`, focused tests.
- Forbidden files: unrelated pig write routes, migrations unless approved.
- Data/migration impact: none expected.
- Test plan: allocation rows link to review/pig detail, preview remains required, no classified reclassification without allowed flow.
- Pressure-test plan: classified pig, unclassified pig, stale weight, missing weight, owner apply denied/allowed path, rollback of UI-only navigation.
- Acceptance criteria: owner can safely review and assign purpose with audit trail and owner approval.
- Rollback plan: revert UI/navigation additions.

## OP-005 Beacon Full-Width Command UI Plan

- Owner decision captured: Beacon page is squeezed/confusing; plan UI improvement after operational blockers; do not change posting/public execution behavior.
- Routes/files identified: `/sales/beacon-media`; `templates/beacon-media.html`, `static/css/beaconMedia.css`, `static/js/beaconMedia.js`, route contract tests.
- Source-of-truth confirmed: existing Beacon media APIs and media library.
- Proposed direction: full-width command workflow with media list, selected asset review, policy gates, and publish-state separation.
- What not to do: no public posting shortcuts, no posting policy changes, no asset generation, no external media cleanup.
- Risk level: medium.
- Confidence score: 92%.
- Missing evidence: live screenshot/browser behavior and primary Beacon workflow decision.
- Implementation phase/batch: OP-BUILD-6.
- Allowed files later: Beacon template/CSS/JS and tests.
- Forbidden files: posting execution routes, `static/assets`, screenshots, `external_sources`.
- Data/migration impact: none expected.
- Test plan: desktop full-width layout, no horizontal scroll, policy gates visible, no public post button added.
- Pressure-test plan: 1366px desktop, tablet, mobile, no overlap, no public post mutation, degraded/empty media state.
- Rollback plan: revert layout changes.

## OP-006 Pig Detail Full-Width Web View Plan

- Owner decision captured: Pig detail should use full dashboard width; UI-only later unless data issues are discovered.
- Routes/files identified: `/pig/<pig_id>`, `/api/pig-weights/pig/<pig_id>`; `templates/pig-detail.html`, `static/js/pigDetail.js`, `static/css/main.css`, pig detail service, route contract tests.
- Source-of-truth confirmed: Google Sheets pig overview/master data through `get_pig_detail()`.
- Proposed direction: full-width pig profile with identity, lifecycle, weight, health, movement, family, purpose, and action links.
- What not to do: no lifecycle/death behavior changes, no write shortcuts, no data source change.
- Risk level: medium.
- Confidence score: 93%.
- Missing evidence: live page inspection and first-viewport priority decision.
- Implementation phase/batch: OP-BUILD-6.
- Allowed files later: pig detail template/JS/CSS and route contract tests.
- Forbidden files: pig write routes, migrations, assets.
- Data/migration impact: none expected.
- Test plan: route contract, desktop full-width layout, mobile stacking, lifecycle controls still guarded.
- Pressure-test plan: real pig id, missing pig id, mobile, desktop, long history, no write shortcut regression.
- Rollback plan: revert template/CSS changes.

## OP-007 Sales Dashboard Meat-Ready Stock Visibility

- Owner clarification captured: meat-ready stock means animals safely available for the meat-sales pipeline based on latest known weight, purpose/status, health/hold status, reservation status, and current meat/abattoir settings.
- Proposed categories: Meat Window Candidate; Abattoir/Cull Candidate; Live Sale Candidate; Hold/Grow Longer; Excluded; Slow Grower Review List.
- Routes/files identified: `/sales-dashboard`, `/api/pig-weights/sales-dashboard`; pig weight service/controller, sales dashboard template/JS, route tests.
- Source-of-truth confirmed: `SALES_STOCK_SUMMARY`, `SALES_STOCK_TOTALS`, pig sales availability fields, allocation readiness, and monthly sales transaction summary.
- Evidence: current dashboard API returns stock summary/totals from Sheets views, not an explicit meat-ready-stock model; live response was not inspected.
- Proposed direction: add explicit meat-ready stock cards/empty states using allocation readiness and stock summary data, linked to OP-003 settings.
- What not to do: do not invent stock, reserve stock, or change SAM availability automatically.
- Risk level: medium.
- Confidence score: 95%.
- Missing evidence: live `/api/pig-weights/sales-dashboard` response or sheet sample to prove whether zero means no qualifying animals or missing query/model.
- Exact test needed: dashboard response with qualifying meat-window animal, no qualifying animals, and missing sheet rows.
- Implementation phase/batch: OP-BUILD-4 after OP-003.
- Allowed files later: pig weight service, sales dashboard JS/template, focused tests.
- Forbidden files: sales mutation routes, reservation/payment code, migrations unless approved.
- Data/migration impact: none if derived from current sheets.
- Test plan: meat-ready stock present, no-stock empty state, stock categories, no mutation.
- Pressure-test plan: stale weights, no weight, reserved animals, heavy cull animals, boundary weights, sold/dead/sick/hold exclusions.
- Acceptance criteria: owner can tell whether meat-ready stock exists and why the dashboard shows zero.
- Rollback plan: remove derived meat-ready card/summary.

## OP-008 Current Stock Value And Sale Readiness Model

- Owner decision captured: estimate current sellable value, not feed-cost profitability; no feed cost for now; use current configured sale prices, latest reliable weight, purpose/status/category, and decision groups.
- Proposed valuation groups: Meat Window Candidate Value; Abattoir/Cull Candidate Value; Live Sale Candidate Value; Hold/Grow Longer Estimated Future Value; Excluded/No Value Yet; Slow Grower Review List.
- Routes/files identified: likely `/sales-dashboard`, `/pig-allocation`, `/meat-planning`, future read-only valuation endpoint; pig weight service, price book/read services, dashboard/allocation JS/templates.
- Source-of-truth confirmed: pig overview/master data, allocation readiness, sales stock sheets, meat price book, and sales transaction summaries.
- Evidence: meat price book source is confirmed; stock/weight source is confirmed at service level; category-to-price mapping and live data quality are not confirmed.
- Valuation basis: current configured sale prices only, no feed cost, latest reliable weight, purpose/status/category, route/category grouping, confidence when weight is stale or missing.
- Future livestock sales link: can later seed livestock sale readiness, but must not promise stock to SAM until criteria and owner approval are met.
- What not to do: no promised sale price, no customer-facing valuation, no SAM availability change, no accounting truth without approval.
- Risk level: high.
- Confidence score: 92%.
- Missing evidence: live data examples, owner approval of category-to-price mapping, and exact stale-weight threshold.
- Exact test needed: valuation with configured price, missing price, stale weight, missing weight, reserved animal, heavy cull, and slow grower.
- Implementation phase/batch: OP-BUILD-4 after OP-003 and OP-007.
- Allowed files later: planning doc first; later pig weight service, price book/read services, dashboard JS/template, tests.
- Forbidden files: accounting/payment routes, customer pages, migrations unless approved.
- Data/migration impact: none for prototype; possible durable valuation assumptions table later.
- Test plan: buckets, price basis display, missing price degraded state, no stock mutation, no customer output.
- Pressure-test plan: stale weights, no weight, reserved animals, heavy cull animals, boundary weights, missing price book, category conflict.
- Rollback plan: remove valuation card/service.
- Owner decision still needed: exact category-to-price mapping and stale-weight threshold.

## OP-009 SAM Pilot Readiness 500 Fix

- Owner decision captured: investigate before Phase 3A.6; do not bundle with Phase 3A.6; fix only after root cause is known.
- Routes/files identified: `/sales/meat-leads`, `/api/sales/meat-pilot-readiness`; `modules/sales/meat_pilot_readiness.py`, `modules/sales/sales_transaction_routes.py`, `static/js/meatSalesLeads.js`, `tests/test_sales_transaction_routes.py`, Playwright SAM spec.
- Source-of-truth confirmed: sales leads, preorder contract, quote packet, meat ops, and template pack readiness.
- Evidence: frontend calls `/api/sales/meat-pilot-readiness?limit=50&status=launch_test`; backend loops through leads and calls contract, quote, and ops services without per-source degraded exception handling.
- Likely fix direction: make readiness source-degraded per lead and route-level safe; return 200 with degraded metrics unless lead list itself is unavailable.
- What not to do: do not hide failure, change send/payment/reservation behavior, switch command-state frontend, or call mutation endpoints.
- Risk level: medium.
- Confidence score: 95%.
- Missing evidence: Render traceback, local reproduction with production-like lead data, or targeted test proving a contract/quote/ops exception causes the current 500.
- Exact test needed: patch one per-lead source to raise and prove current endpoint fails; implementation test should prove it returns 200 degraded after fix.
- Implementation phase/batch: OP-BUILD-1 if narrow and no migration required.
- Allowed files later: `modules/sales/meat_pilot_readiness.py`, `tests/test_sales_transaction_routes.py`, maybe `static/js/meatSalesLeads.js` for degraded wording.
- Forbidden files: mutation routes, command-state frontend switch, templates/CSS unless approved.
- Data/migration impact: none expected.
- Test plan: route returns 200 with degraded row if contract/quote/ops fails; frontend shows degraded readiness not 500.
- Pressure-test plan: no leads, one good lead, one bad source, all bad sources, list-sales failure, timeout/degraded wording, no unsafe action proof.
- Acceptance criteria: `/sales/meat-leads` no longer shows raw 500 for readiness.
- Rollback plan: revert readiness degradation change.

## OP-010 Owner Logout Redirect Preference

- Owner decision captured: logout should redirect to the main dashboard after sign-out, not owner login by default.
- Routes/files identified: `/owner/logout`, `/owner/login`, `/sales/meat-leads`, `/`; `modules/auth/owner_access.py`, `app.py`, `templates/owner-login.html`, `templates/meat-sales-leads.html`, `tests/test_owner_access.py`.
- Source-of-truth confirmed: Flask session/cookie owner access helpers.
- Evidence: `/` is the main dashboard route rendering `dashboard.html`; `owner_logout_post()` clears the session and currently redirects to `owner_login_page`; owner access tests passed.
- Recommended exact target: `url_for("dashboard")`, which resolves to `/`.
- Proposed solution direction: change post-logout redirect to `url_for("dashboard")`; preserve session clearing and protected page denial after logout.
- What not to do: do not keep owner session alive, weaken guards, or put tokens in JS/templates.
- Risk level: low.
- Confidence score: 98%.
- Missing evidence: none.
- Implementation phase/batch: OP-BUILD-1.
- Allowed files later: `modules/auth/owner_access.py`, `tests/test_owner_access.py`; `app.py` only if route wrapper adjustment is needed.
- Forbidden files: sales route logic, SAM business JS, auth weakening, `.env`.
- Data/migration impact: none.
- Test plan: logout clears session, redirects to `/`, protected pages deny after logout, command-state denies after logout, no token exposure.
- Pressure-test plan: logout from SAM, logout from owner status, expired/no session logout, access enabled remote, access disabled local, no secret leakage.
- Acceptance criteria: owner lands on dashboard after logout and must log in again for protected owner pages.
- Rollback plan: redirect back to `/owner/login`.

## OP-1.1 Superseded Build Order

The OP-1.1 build-order section is superseded by the OP-1.2 Evidence Push Update below. Use the OP-1.2 confidence table and recommended build packages as the active plan.

## OP-1.2 Evidence Push Update

Date: 2026-06-28

Evidence log: `docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md`

### Read-Only Evidence Summary

- Supabase read-only inspection found actual sales lead rows for Sinethemba, Pappa G, and Thando. Each was a `new` inbound Chatwoot lead with `interest_product_type=unknown` and missing cut/location/timing facts. IDs and raw notes were not printed.
- Supabase read-only inspection confirmed 31 sales leads, 188 sales lead events, and 5 active meat price book entries/groups.
- Google Sheets/service read-only inspection confirmed sales dashboard data exists as top-level `summary` and `totals`, with 6 total rows and 21 summary rows. Categories include Ready for Slaughter, but the dashboard does not expose an explicit meat-ready model.
- Pig allocation readiness read-only inspection confirmed 217 rows and current code-default thresholds. It currently reports 3 Meat Candidate rows.
- Non-mutating 71-row bulk pressure probe showed simulated failure after 60 rows returns HTTP 201 with `success=true`, `saved_count=60`, and `failed_count=11`; this proves the partial-success safety issue and fix direction.
- Non-mutating SAM pilot readiness probe showed a per-lead source exception bubbles out of `get_meat_pilot_readiness()` instead of degrading; this proves the 500 failure class.

### Updated Confidence Scores

| Ticket | Confidence | Build status | Evidence basis |
| --- | ---: | --- | --- |
| OP-001 Meat Lead Creation And Qualification | 96% | Build-ready after OP-1.2 approval | Real weak owner-labeled chats are lead rows with unknown product and missing actionable facts. |
| OP-002 Bulk Weight Reliability And Audit Trail | 96% | Build-ready after OP-1.2 approval | 71-row mocked failure proves current partial-success behavior and audit gap. |
| OP-003 Meat Planning Weight Window Settings | 97% | Build-ready after OP-1.2 approval | Current thresholds and affected readiness services confirmed; owner boundary rule captured. |
| OP-004 Pig Allocation Purpose Review Workflow | 94% | Blocked | Needs live owner workflow inspection. |
| OP-005 Beacon Full-Width Command UI Plan | 92% | Blocked | Needs browser/UI inspection. |
| OP-006 Pig Detail Full-Width Web View Plan | 93% | Blocked | Needs browser/UI inspection. |
| OP-007 Sales Dashboard Meat-Ready Stock Visibility | 96% | Build-ready after OP-1.2 approval | Current dashboard source and allocation readiness source confirmed; explicit meat-ready model missing. |
| OP-008 Current Stock Value And Sale Readiness Model | 96% | Build-ready after OP-1.2 approval | Price book, sales stock price ranges, allocation/weight source, and owner freshness/value rules confirmed. |
| OP-009 SAM Pilot Readiness 500 Fix | 96% | Build-ready after OP-1.2 approval | Targeted failing probe proves per-lead source exception is not degraded. |
| OP-010 Owner Logout Redirect Preference | 98% | Build-ready after OP-1.2 approval | `/` dashboard route and current `/owner/login` logout redirect confirmed. |

### OP-001 Build Notes

- Implement a qualification classifier before surfacing leads in SAM Command Room.
- One-word/greeting/name-only messages become `raw_conversation_event`, `intake_candidate`, `needs_auto_qualification`, or `disqualified_or_noise`, not `qualified_meat_lead`.
- A real `qualified_meat_lead` requires contact/conversation identity, product intent, at least one actionable sales fact, and enough content to distinguish buying intent from noise.
- Auto-follow-up must remain inside existing Chatwoot/WhatsApp, opt-in, template, 24-hour window, env flag, approval hash, and Gatekeeper rails. If send is blocked, create draft/follow-up task instead.

### OP-002 Build Notes

- Choose a two-phase approach: immediate Sheets safety patch, then Supabase durable rail if Sheets remains structurally unreliable.
- Immediate build must add or expose operation id, expected count, processed count, success count, failed count, duplicate/skipped count, per-row result trail, retry guidance, and clear UI summary.
- Partial success must not be presented as plain success.

### OP-003 / OP-007 / OP-008 Build Notes

- Update meat/abattoir logic around owner defaults: meat 60kg to below 80kg; abattoir/cull 80kg+.
- Meat-ready stock depends on OP-003 settings and must exclude reserved/sold/dead/sick/hold/breeding keepers and missing-reliable-weight animals.
- Stock value should use current configured prices only: Supabase price book for meat routes where applicable, sales stock price ranges/settings for live categories where applicable, and `pricing_not_configured` when no current source exists.
- Freshness rule: 0-14 days fresh; 15-30 days stale warning; older than 30 days not valuation-ready unless owner manually approves/reweighs.

### OP-009 Build Notes

- Fix readiness before Phase 3A.6.
- Add tests where contract, quote, and ops source failures return degraded payloads instead of 500.
- Broken lead/source must not break the full readiness response.

### Recommended Build Packages After OP-1.2

#### OP-BUILD-1A Tiny Live Fixes

- OP-010 Owner Logout Redirect Preference.
- OP-009 SAM Pilot Readiness 500 Fix.

#### OP-BUILD-2 Pig Tracker Reliability

- OP-002 Bulk Weight Reliability And Audit Trail.

#### OP-BUILD-3 Meat Lead Quality

- OP-001 Meat Lead Creation And Qualification.

#### OP-BUILD-4 Meat Planning, Stock Visibility, And Value

- OP-003 Meat Planning Weight Window Settings.
- OP-007 Sales Dashboard Meat-Ready Stock Visibility.
- OP-008 Current Stock Value And Sale Readiness Model.

#### Still Blocked

- OP-004 Pig Allocation Purpose Review Workflow.
- OP-005 Beacon Full-Width Command UI Plan.
- OP-006 Pig Detail Full-Width Web View Plan.

#### Then

- Phase 3A.6 SAM frontend consumes command-state with fallback only after OP-009 is fixed or proven to degrade safely in production.

