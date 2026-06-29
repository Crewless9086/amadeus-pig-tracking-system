# Scratch (`planning/ToDoList.md`)

# Processed Notes

## 2026-06-29 GS-MIG-6 Conflicting Weight Review And Reconciliation

Status: active.

Branch: `gs-mig-6-conflict-review-reconciliation`

Output:

- `docs/06-operations/GS_MIG_6_CONFLICTING_WEIGHT_REVIEW.md`

Result:

- Generated owner/admin review output for the 9 conflicting same-pig/same-date weight groups.
- Verified all imported Supabase table counts match the GS-MIG-5 policy payload.
- Verified all 9 conflicting-weight keys have 0 imported canonical rows.
- No Google Sheets writes.
- No Supabase writes.
- No app route cutover.

Next:

- Owner/admin must decide each conflicting group later: choose canonical weight, exclude group, or correct the source and reimport through a controlled path.
- After review output is accepted, continue to route-by-route shadow verification before any Supabase read cutover.

## 2026-06-29 GS-MIG-5 Controlled Import Execution

Status: complete.

Import batch: `GS-MIG-5-2026-06-29`

Result:

- Imported clean canonical farm data into Supabase.
- Imported 217 pigs, 20 pens, 1,190 weight events, 179 location events, 261 medical events, 17 litters, 15 mating events, 3 products, and 18 settings.
- Populated `pig_current_state`, `pig_latest_location_events`, and `pig_latest_weight_events`.
- No Google Sheets writes.
- No app route cutover.
- 9 conflicting same-pig/same-date weight groups remain excluded for review.

Report:

- `docs/06-operations/GS_MIG_5_IMPORT_EXECUTION_REPORT.md`

Next:

- GS-MIG-6 should produce owner/admin review output for conflicting weights and verify imported Supabase rows before any route cutover.

## 2026-06-29 GS-MIG-5 Initial Import Plan

Status: merged as PR #24; import execution completed separately.

Branch: `gs-mig-5-initial-import-plan`

Owner update:

- Owner cleaned Google Sheets by removing/fixing some missing-`Pig_ID` `WEIGHT_LOG` items.

Fresh read-only verifier result:

- Missing-`Pig_ID` quarantine is now 0.
- 1,235 original mapped weight events become 1,190 canonical weight events.
- 185 original mapped movement events become 179 canonical movement events.
- 35 review items remain.
- 26 review items are auto-resolved dedupes.
- 9 review items are pending conflicting-weight owner/admin review.

Plan:

- Initial import can import clean canonical data while excluding the 9 conflicting-weight groups.
- Do not import data or cut over app routes until owner explicitly approves GS-MIG-5 import execution.

## 2026-06-29 GS-MIG-4 Additive Schema Apply

Status: complete.

Applied migration:

- `supabase/migrations/202606290001_create_farm_canonical_tables.sql`

Result:

- Created empty canonical farm tables/views in Supabase.
- Verified all new tables exist and contain 0 rows.
- Verified migration log entry exists.
- No farm data imported.
- No Google Sheets data changed.
- No app route cutover.

Verified tables/views:

- `pens`
- `pigs`
- `farm_products`
- `app_settings`
- `pig_weight_events`
- `pig_location_events`
- `pig_medical_events`
- `litters`
- `mating_events`
- `pig_latest_weight_events`
- `pig_latest_location_events`
- `pig_current_state`

## 2026-06-29 GS-MIG-3 Backfill Verifier

Status: merged as PR #23.

Branch: `gs-mig-3-review-backfill-verifier`

Scope:

- Produce review/quarantine output under the owner-approved import policies.
- Produce controlled canonical payload counts before any migration apply/import.
- Do not apply migrations or write production Supabase/Google Sheets data.
- Do not cut over app routes.

Dry-run verifier result:

- 1,235 original mapped weight events become 1,190 canonical weight events.
- 185 original mapped movement events become 179 canonical movement events.
- 41 review items are generated.
- 26 review items are auto-resolved dedupes.
- 9 review items are pending conflicting-weight owner/admin review.
- 6 review items are quarantined missing-`Pig_ID` weight rows.
- Import readiness remains false until the 15 pending/quarantined items are accepted as excluded or resolved.

## 2026-06-29 GS-MIG-3B Import Policy Decisions

Status: merged as PR #22.

Branch: `gs-mig-3b-import-policy`

Owner decisions:

- Missing `Pig_ID` weight rows: leave out of canonical import and list in review/quarantine output.
- Same-weight duplicates: import one canonical event only; preserve source references.
- Conflicting same-pig/same-date weights: do not auto-import; put them on a visible review list.
- Repeated movements: import one canonical movement only; preserve source references.

Conflicting-weight review rule:

- Conflicts must show pig id, date, candidate weights, source sheet rows, and `Weight_Log_ID` values.
- Until reviewed, they must not affect current weight, meat readiness, allocation, or stock valuation.
- Later owner/admin choices should be: choose canonical value, exclude group, or approve a correction rule.

## 2026-06-29 GS-MIG-3A Data Issue Review

Status: merged as PR #21.

Branch: `gs-mig-3a-data-issue-review`

Scope:

- Classify data-quality blockers before migration apply/import.
- Do not apply migrations or write production Supabase/Google Sheets data.
- Do not cut over app routes.

Read-only issue report result:

- 6 `WEIGHT_LOG` rows have `Weight_Log_ID` but no `Pig_ID`.
- 34 same-pig/same-date weight duplicate groups exist.
- 25 weight duplicate groups have the same weight value and are likely duplicate artifacts.
- 9 weight duplicate groups have conflicting values and need owner/admin review.
- 1 repeated movement group exists: `PIG-2026-9613|2026-06-22|PEN-012`, 7 rows, likely duplicate same movement.

Recommended policy for review:

- Missing `Pig_ID`: identify pig or exclude/quarantine.
- Same-weight duplicates: import one canonical event and preserve source references.
- Conflicting weights: do not auto-import until owner/admin policy is approved.
- Repeated movement: import one canonical movement and preserve source references.

## 2026-06-29 GS-MIG-2 Reconciliation

Status: merged as PR #20.

Branch: `gs-mig-2-reconciliation`

Scope:

- Strengthen read-only Google Sheets to Supabase reconciliation before any migration apply/import.
- Report source sheet counts, target payload counts, excluded rows, duplicate candidates, formula count comparisons, and import readiness.
- Do not apply migrations or write production Supabase/Google Sheets data.
- Do not cut over app routes yet.

Read-only reconciliation result:

- 217 pigs
- 1,235 mapped weight events from 1,241 `WEIGHT_LOG` rows
- 185 location events
- 261 medical events
- 20 pens
- 17 litters
- 15 mating events
- 3 products
- 18 settings
- 6 `WEIGHT_LOG` rows excluded because `Pig_ID` is missing
- 34 same-pig/same-date weight duplicate keys need review
- 1 repeated location movement key needs review: `PIG-2026-9613|2026-06-22|PEN-012`

## 2026-06-29 GS-MIG-1 Canonical Schema And Dry-Run Import

Status: merged as PR #19.

Branch: `gs-mig-1-canonical-schema-dry-run`

Scope:

- Add canonical farm schema migration proposal.
- Add dry-run Google Sheets import/reconciliation tooling.
- Add tests proving dry-run behavior and link issue reporting.
- Do not apply migrations or write production Supabase/Google Sheets data.
- Do not cut over app routes yet.

Dry-run result:

- 217 pigs
- 1,235 weight events
- 185 location events
- 261 medical events
- 20 pens
- 17 litters
- 15 mating events
- 3 products
- 18 settings
- 6 `WEIGHT_LOG` rows excluded because `Pig_ID` is missing

## 2026-06-29 Google Sheets To Supabase Migration Deep Dive

Status: plan-only.

Branch: `gs-to-supabase-deep-dive-plan`

Decision direction:

- Supabase may need to become the canonical operational database.
- Google Sheets should become legacy reference, backup/export, and optional reporting.
- No implementation, migrations, production writes, Google Sheets edits, formula changes, or destructive cleanup are approved in this phase.
- Bulk weights exposed the larger dependency problem: formulas, Sheets reads/writes, timeouts, partial writes, and hidden operational state.

Plan file:

- `docs/06-operations/GOOGLE_SHEETS_TO_SUPABASE_MIGRATION_PLAN.md`

## 2026-06-29 One-Button Bulk Owner Flow

Status: active P0 live fix.

Branch: `p0-bulk-one-button-owner-flow`

Staged batch id: `2241aeab-4f40-4797-882d-1588a17abbd0`

Owner live result:

- The screen still exposed Continue Upload, batch id, `non_json_response`, and technical upload mechanics.
- Owner needs one primary action: Upload Weights.
- Upload Weights must stage, resume, process, retry, and pause safely in the background.

Read-only inspection:

- Batch status is `processing`.
- 10 rows are stuck in `processing`.
- 32 rows remain `staged`.
- 31 rows are already recorded duplicate weights.
- 43 rows are blank/no-change skipped.
- No production processing was run during inspection.

Decision:

- Hide separate Continue Upload from the normal owner flow.
- Keep Save Draft, Upload Weights, Download Draft, and Import Draft.
- Pressing Upload Weights must resume an existing `batch_id`, recover interrupted `processing` rows, and avoid exposing JSON/status/batch mechanics as the main owner message.

## 2026-06-29 Staged Batch Auto-Process

Status: active P0 live fix.

Branch: `p0-staged-batch-auto-process`

Staged batch id: `2241aeab-4f40-4797-882d-1588a17abbd0`

Owner live result:

- UI said no actionable rows while Upload Progress showed 42 remaining.
- Existing staged batch did not visibly continue processing.

Read-only inspection:

- 42 rows are staged/processable.
- 31 rows are already recorded duplicate weights.
- 43 rows are blank/no-change skipped.
- No production processing was run during inspection.

Decision:

- Recover saved `batch_id` on page load.
- Show Continue Upload when rows remain.
- Upload Weights must process an existing batch id instead of creating a new batch or saying no actionable rows.

## 2026-06-29 Simple Bulk Upload UX

Status: active P0 UX fix.

Branch: `p0-bulk-simple-auto-upload`

Owner live result after durable rail deploy:

- The page exposed Stage Batch and backend-style remaining-row mechanics.
- Batch Review showed 0 visible/actionable rows even though a saved draft/batch had rows.
- The owner could not see an obvious way to finish uploading.

Decision:

- Keep the Supabase-first durable rail.
- Hide staging/chunking from the owner.
- Owner-facing flow must be Save Draft, Upload Weights, Download Draft, Import Draft.
- Upload Weights must stage and process automatically.

## 2026-06-28 Supabase-First Durable Bulk Rail

Status: active P0 build.

Branch: `p0-bulk-supabase-durable-rail`

Evidence log: `docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md`

Owner live result after JSON-safe hotfix:

- 73 bulk-weight entries were restored from draft and uploaded for 2026-06-22.
- About 21 rows included pen changes.
- The old synchronous endpoint still returned non-JSON HTML from `POST /api/pig-weights/weights-batch`.
- Batch Review showed 116 visible, 73 actionable, 0 weight rows, 0 pen changes, 0 processed, 43 skipped, 0 blocked, 0 failed.

Decision:

- Build a Supabase-first durable staging/audit rail for bulk weights.
- Process rows in chunks and keep Google Sheets as downstream sync.
- Add Import Draft so downloaded drafts can be restored without retyping.
- Do not ask for another large manual owner retest until automated 73-row + 21 pen-change pressure tests pass and the durable rail is deployed.

## 2026-06-28 Bulk Weight Live Failure

Status: escalated to P0 data-loss fix.

Branch: `p0-bulk-weight-draft-recovery`

Evidence log: `docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md`

Owner live result:

- 71 bulk-weight rows entered.
- 60 rows were recorded before upload.
- Save Draft and Upload Batch ended in a vague error.
- Refresh lost all entered rows.

Requirement:

- Do not ask the owner to manually re-enter the 71-row test until draft recovery, upload-failure retention, partial-failure handling, and download/export pressure tests pass and the fix is deployed.

## 2026-06-28 Bulk Upload HTML/JSON Failure

Status: escalated to P0 upload-pipeline JSON fix.

Branch: `p0-bulk-upload-json-durable`

Evidence log: `docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md`

Owner live result:

- 73 bulk-weight entries entered.
- About 21 rows included pen changes.
- Upload returned HTML/non-JSON and the browser showed `Unexpected token '<'`.
- Batch Review showed 73 expected, 0 processed, 43 skipped, 0 blocked, 0 failed.
- Draft recovery appears to have kept the draft available.

Requirement:

- Do not ask the owner to manually re-enter or retest large batches until non-JSON response handling, JSON route error envelopes, 73-row + pen-change pressure tests, and draft preservation tests pass and the fix is deployed.

## 2026-06-28 Operational Notes

Status: moved to operational plan

OP-1.1 status: owner decisions incorporated into the operational master plan; tickets require 96%+ confidence and pressure-test plans before implementation.

OP-1.2 status: read-only evidence push added Supabase/Sheets/service summaries, non-mutating pressure probes, and updated confidence gates in the operational master plan and evidence log.

Plan file: `docs/06-operations/OPERATIONAL_FIXES_MASTER_PLAN.md`

Processed copy: `planning/inbox/processed/2026-06/ToDoList_2026-06-28_operational_notes.md`

Tickets:

- OP-001 Meat Lead Creation And Qualification
- OP-002 Bulk Weight Reliability And Audit Trail
- OP-003 Meat Planning Weight Window Settings
- OP-004 Pig Allocation Purpose Review Workflow
- OP-005 Beacon Full-Width Command UI Plan
- OP-006 Pig Detail Full-Width Web View Plan
- OP-007 Sales Dashboard Meat-Ready Stock Visibility
- OP-008 Current Stock Value And Sale Readiness Model
- OP-009 SAM Pilot Readiness 500 Fix
- OP-010 Owner Logout Redirect Preference

Raw notes remain preserved below and were copied into the processed inbox file.

## Triage Status

Triaged into `docs/00-start-here/NEXT_STEPS.md` on 2026-06-28 during CLEANUP-4B.

Key headings triaged:

- meat lead creation quality.
- bulk weight reliability.
- meat planning weight windows.
- pig allocation workflow.
- Beacon full-width UI.
- pig detail full-width layout.
- sales stock/value questions.
- SAM pilot readiness 500.
- Logout redirect preference.

Triaged into `docs/00-start-here/NEXT_STEPS.md` on 2026-06-28.

Raw notes are preserved below. Do not delete owner notes from this file unless the owner explicitly approves clearing processed items.

Use this **only** for fleeting notes before they land in the real plan.

Canonical build order: **`docs/00-start-here/NEXT_STEPS.md`**.

**Handoff:** Big / cross-cutting reviews -> **`docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md`**. Roles, phase queue, flexible testing: **`docs/00-start-here/HOW_WE_WORK.md`**; **`CLAUDE.md`** at repo root.

**Workflow**

1. Jot bullets here while you discover work.
2. Move each item into **`NEXT_STEPS.md`** under the right phase, or into the relevant canonical docs file.
3. **Delete those lines from this file** once they are documented.

Keep this list empty, or nearly empty, so nothing drifts out of **`NEXT_STEPS.md`**.

## Moved To Canonical Docs

- Pork sales business model moved to `docs/08-business-modules/PORK_SALES_MODEL.md`.
- Roadmap slot added under `NEXT_STEPS.md` Phase 11: Pork Sales Business Module.
- 2.1 weather sub-agent LLM error moved to `NEXT_STEPS.md` as Phase 7.3E quick triage and noted in the `2.1` workflow README.
- Web-app printing/printer discovery moved to `NEXT_STEPS.md` Phase 9.6.
- Oom Sakkie navigation buttons moved to `NEXT_STEPS.md` Phase 7.3F.
- Farm home/dashboard idea moved to `NEXT_STEPS.md` Phase 10.
- Matings tile sorting moved to `NEXT_STEPS.md` Phase 8E.
- Fertility, bloodline, and breeding suggestions moved to `NEXT_STEPS.md` Phase 8F.
- Litter attention/weaning workflow notes moved to `NEXT_STEPS.md` Phase 9.1C.
- Weight form UX notes moved to `NEXT_STEPS.md` Phase 9.3B.
- Pig list tag-formatting note moved to `NEXT_STEPS.md` Phase 9.2B.
- Mobile/PWA and desktop layout notes moved to `NEXT_STEPS.md` Phase 10.4/farm home dashboard planning.
- Sunsynk Eskom tariff/value calculation note moved to `NEXT_STEPS.md` Phase 10.3M and `SUPABASE_TELEMETRY_PLAN.md`.
- n8n future-role question answered in `SUPABASE_TELEMETRY_PLAN.md` and summarized under `NEXT_STEPS.md` Phase 10.3M.
- Human alerts vs automation triggers note moved to `NEXT_STEPS.md` Phase 10.3M and `SUPABASE_TELEMETRY_PLAN.md`.
- Dashboard slaughter sale count/value note moved to `NEXT_STEPS.md` Phase 9.5B.
- Multi-recipient Telegram alert/notification note moved to `NEXT_STEPS.md` Phase 10.3M.
- Slaughter update form/modal UX note moved to `NEXT_STEPS.md` Phase 10 slaughter form refinement notes.
- Litter attention action-path note moved to `NEXT_STEPS.md` Phase 9.1C.
- Full sales summary screen note moved to `NEXT_STEPS.md` Phase 9.5B.
- Mating attention group/reason note moved to `NEXT_STEPS.md` Phase 8F.
- Bulk weight-entry from printable capture sheet note moved to `NEXT_STEPS.md` Phase 9.6C.
- Herd dashboard total/breakdown audit note moved to `NEXT_STEPS.md` Phase 10 farm home/dashboard follow-ups.
- Farm attention Telegram reminder note moved to `NEXT_STEPS.md` Phase 10 farm home/dashboard follow-ups.
- Farm task/reminder/project management note moved to `NEXT_STEPS.md` Phase 10 farm home/dashboard follow-ups.
- Telegram alert emoji/formatting note moved to `NEXT_STEPS.md` Phase 10 farm home/dashboard follow-ups.
- Weather/solar dashboard symbol note moved to `NEXT_STEPS.md` Phase 10 farm home/dashboard follow-ups.
- Windy weather-station integration research note moved to `NEXT_STEPS.md` Phase 10 farm home/dashboard follow-ups.
- Future alert-preference page note moved to `NEXT_STEPS.md` Phase 10 farm home/dashboard follow-ups.
- Litter vaccination, earmarking, deworming, printable sheet, and bulk capture note moved to `NEXT_STEPS.md` Phase 9.7F future litter health/reminder capture planning.
- Litter newborn-health live-test result, wean/tag timing correction, fast piglet death capture, and smart return navigation moved to `NEXT_STEPS.md` Phase 9.7F-I.
- 35-day weaning default, closest-Monday planning option, dead pig rows for history, accepted death reasons, and future litter print/capture sample note moved to `NEXT_STEPS.md` Phase 9.7G-H2.
- Practical Telegram alert timing/rain summaries/formatting note moved to `NEXT_STEPS.md` Phase 10 farm home/dashboard follow-ups.
- Slack multi-agent collaboration architecture assessment moved to `docs/01-architecture/SLACK_ARCHITECTURE_ASSESSMENT.md`; recommendation is keep for future phase as optional human visibility layer only, not agent memory or source of truth.
- Oom Sakkie Trillion-style prompt/playbook pack moved to `docs/01-architecture/OOM_SAKKIE_AGENT_PROMPT_LIBRARY.md`, `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md`, `docs/00-start-here/NEXT_STEPS.md`, and `docs/00-start-here/CURRENT_STATE.md`; immediate build remains read-only `/oom-sakkie` kiosk plus orchestrator before voice/PWA/security/factory layers.
- Claude review of the Oom Sakkie PRD moved to `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md`, `docs/00-start-here/NEXT_STEPS.md` Phase 10.6A, and `docs/00-start-here/CURRENT_STATE.md`; backend-as-brain was confirmed on 2026-06-06, with n8n/GateKeeper remaining Telegram I/O and a feature-flagged parallel Telegram migration required later.
- Oom Sakkie future specialist-agent roster moved to `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`, `docs/00-start-here/NEXT_STEPS.md` Phase 10.7, and `docs/00-start-here/CURRENT_STATE.md`; this is planning only, with no live delegation/autonomous agents/write tools.

Add new scratch bullets below, then move them into the correct canonical file.
- Oom Sakkie analyst/review helper moved to `NEXT_STEPS.md` Phase 10.7B and `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`: advisory review queue only for now; no automatic trace marking or autonomous loop.
- Bulk-weight 20-vs-68 live-data note moved to `NEXT_STEPS.md` Phase 9.6C and `CURRENT_STATE.md`; local report visibility correction is ready for browser/live confirmation.
- Litter `LIT-2026-EB92` male/female sex-count capture note moved to `NEXT_STEPS.md` Phase 9.7J and `CURRENT_STATE.md`; local preview/save action is ready for browser testing.
- 2026-06-16 sales launch repoint moved to `HOW_WE_WORK.md`, `CURRENT_STATE.md`, `NEXT_STEPS.md` Phase 11C, and `PORK_BUSINESS_INTEGRATION_READINESS_MAP.md`: Oom Sakkie UI is parked/not passed; next build is one real manual/inbound lead through the owner-review sales lead rail.
- Telegram Order Alert with buttons/suggested values remains covered by `NEXT_STEPS.md` Phase 1.9 follow-up/internal operations notification planning; do not build it while Phase 11L Chatwoot Sales Hygiene is the active money-test slice.

No active scratch bullets. Move any new note into `NEXT_STEPS.md`, `CURRENT_STATE.md`, or a module doc before implementation.

## Raw Owner Notes Preserved From 2026-06-28

MEAT LEADS:

- Explain how leads work. The owner saw three chats, Sinethemba, Pappa G, and Thando, where short one-word messages appeared to become meat leads. This feels too broad and needs investigation before changing the lead creation rules.

PIG TRACKER IMPROVEMENTS:

- Bulk weight add is not reliably adding all weights or movements. The owner saw a run on the 15th where only 60 entries were added when 71 were expected. Investigate whether this is Google Sheets timeout behavior, whether Supabase should become the rail for this workflow, and how to provide logs/trails.
- Meat planning has meat window and abattoir window settings on `/meat-planning`. Owner wants to understand how to edit them and whether meat window should be 60-80kg with abattoir window at 80kg+.
- Pig allocation at `/pig-allocation` shows recommendations but no obvious review/action workflow for assigning purpose. Plan how the owner should inspect and assign a pig purpose.
- Beacon page `/sales/beacon-media` is squeezed into the side and confusing. Owner wants a clearer, full-width Beacon UI.
- Pig detail page `/pig/PIG-2026-92F3` is also narrow and should use the web dashboard width better.
- Sales Overview `/sales-dashboard` has an Available Stock table. Confirm whether it shows meat-ready stock and add planning if it does not.
- Owner wants a current stock value/estimated value view for livestock, meat, slaughter-to-butcher, slow growers, and sales availability planning.
- SAM Meat Sales Command Room `/sales/meat-leads` shows Pilot Control Room readiness as `--%` with `Pilot readiness unavailable: Request failed: 500`. Investigate.
- SAM Meat Sales Command Room logout currently redirects to sign-in. Owner asks whether logout can redirect to the dashboard instead.



