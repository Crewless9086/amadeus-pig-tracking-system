# Current State

This is the short live-state dashboard for the project. Keep it current after accepted phases, PR merges, and deploys.

## Production State

`origin/main` currently includes:

- `e2e373d` Harden CHARLIE relay activation (#41)
- `8979773` Add CHARLIE build relay foundation (#40)
- `66f7f71` Complete Google Sheets migration final audit (#39)
- `b12e218` Fallback order line sync safely (#38)
- `d099b5f` Fallback order status log writes safely (#37)
- `3d2df49` Read mating pen lookup from Supabase (#36)
- `9a65c58` Use Supabase pen lookup helper (#35)
- `b9a21c8` Read bulk duplicate weights from Supabase (#34)
- `b0aa71a` Create litters through Supabase (#33)
- `1c146bd` Validate purpose review from Supabase (#32)
- `e36c84f` Cut over dashboard summary to Supabase (#31)
- `4f480cd` Default irrigation status to Supabase auto reads (#30)
- `6eab2da` Fix litter lifecycle migration view order (#29)
- `9733173` Continue Supabase operational cutover (#28)
- `61eeec3` Cut over farm reads to Supabase (#27)
- `474d378` Add farm import conflict reconciliation (#26)
- `2bcf347` Record controlled farm data import (#25)
- `df2bfaf` Plan initial farm data import (#24)
- `dd06ee2` Add Sheets backfill verifier (#23)
- `cf0c7f5` Record Sheets import policies (#22)
- `4d0b598` Classify Sheets migration data issues (#21)
- `4263cc8` Add Google Sheets reconciliation gate (#20)
- `b58f7c1` Add farm migration dry-run schema (#19)
- `6c12976` Simplify bulk weight upload flow (#18)
- `357c161` Continue staged bulk weight uploads (#17)
- `86c1836` Simplify durable bulk weight upload
- `206d483` Add durable bulk weight batch rail
- `981f1a5` Return JSON for bulk upload failures
- `bf25c5e` Protect bulk weight drafts from upload failure
- `36738bd` Polish remaining operational review views (#12)
- `ab8e504` Improve operational reliability and stock readiness (#11)
- `a134f0d` Degrade SAM readiness and redirect logout (#10)
- `1e735fa` Record operational evidence and build gates (#9)
- `fe1c71f` Archive local markdown planning docs (#8)
- `afefb5f` Triage owner notes into next steps (#7)
- `ed2f1c3` Add docs inbox and archive governance (#6)
- `2de81f2` Create active start-here docs workflow (#5)
- `560a345` Add owner logout controls (#4)
- `97e63a0` Add owner access session guard for SAM reads (#3)
- `7d7dc7e` Add read-only SAM command state endpoint (#2)
- `e41d4a6` Polish SAM meat sales full-width dashboard
- `f6487da` Improve SAM meat sales command room (#1)
- `ed3a27d` Improve bulk weight duplicate and movement handling

Render deploys from `main` unless the service configuration says otherwise.

## Active Branches / PRs

- PR #12 is merged into `main`.
- Cleanup is complete enough to pause housekeeping.
- OP-BUILD-1A, OP-BUILD-2/3/4, and remaining operational review-view polish are merged.
- P0 draft recovery and JSON-safe upload hotfixes are merged, but owner retest still received app/server HTML from the old synchronous Google Sheets path.
- P0 staged-batch auto-process is merged, but owner live test still exposed backend mechanics: Continue Upload, batch id, `non_json_response`, and contradictory counts.
- Active P0 branch: `p0-bulk-one-button-owner-flow`.
- Live staged batch under inspection: `2241aeab-4f40-4797-882d-1588a17abbd0`. Read-only inspection showed status `processing`, 10 rows stuck in `processing`, 32 rows still `staged`, 31 already-recorded duplicate rows, and 43 blank/no-change skipped rows.
- Current P0 direction: owner-facing flow must be one button only. `Upload Weights` must stage/resume/process/retry automatically, hide technical staging/chunking, and preserve draft/batch on interruption.
- No further owner manual 71/73-row retest should happen until one-button Upload Weights, existing-batch resume, processing-row recovery, non-JSON pause/retry, and count-display tests pass and the fix is deployed.
- Active migration planning branch: `gs-to-supabase-deep-dive-plan`. This is GS-MIG-0 report-only work. No code, migration, production data, Google Sheets, or app behavior change is approved from this plan alone.
- Current migration direction: Supabase should become canonical operational truth; Google Sheets should become legacy reference/export/reporting, not the critical app write/read path.
- GS-MIG-1 is merged as PR #19: schema proposal plus dry-run import/reconciliation tooling.
- GS-MIG-2 is merged as PR #20. No migration has been applied and no production data has been written.
- GS-MIG-3A is merged as PR #21.
- GS-MIG-3B is merged as PR #22.
- GS-MIG-3 is merged as PR #23.
- GS-MIG-4 additive schema apply completed on 2026-06-29.
- Supabase has canonical farm tables/views: `pens`, `pigs`, `farm_products`, `app_settings`, `pig_weight_events`, `pig_location_events`, `pig_medical_events`, `litters`, `mating_events`, `pig_latest_weight_events`, `pig_latest_location_events`, and `pig_current_state`.
- Owner approved import policy direction: skip missing-`Pig_ID` weight rows into review/quarantine output; collapse same-weight duplicates to one canonical event; hold conflicting same-pig/same-date weights for review; collapse repeated movement duplicates to one canonical movement.
- GS-MIG-5 initial import plan is merged as PR #24.
- GS-MIG-5 controlled import execution completed on 2026-06-29 using import batch `GS-MIG-5-2026-06-29`.
- Supabase canonical farm tables now contain: 217 pigs, 20 pens, 1,190 weight events, 179 location events, 261 medical events, 17 litters, 15 mating events, 3 farm products, and 18 app settings.
- Derived views are populated: `pig_current_state` 217 rows, `pig_latest_location_events` 113 rows, and `pig_latest_weight_events` 155 rows.
- The 9 conflicting same-pig/same-date weight groups remain excluded from canonical import for owner/admin review.
- GS-MIG-6 is merged as PR #26.
- GS-MIG-7 is merged as PR #27. Safe read-only farm routes now prefer Supabase canonical reads with Google Sheets fallback.
- GS-MIG-8/9 is merged as PR #28.
- GS-MIG-8 live order import applied import batch `IMPORT-20260629-LIVE-ORDERS-V1`: 26 orders, 103 order lines, 38 order intakes, 11 intake items, 6 documents, 62 status logs, and 21 pricing rows.
- GS-MIG-8 app cutover: order list/detail/search read from Supabase; order document reads prefer Supabase; daily order reports read Supabase status logs; order create/update/line/reservation/lifecycle and intake update/reset use guarded Supabase write rails when `DATABASE_URL` is available, with Sheets fallback when unavailable.
- GS-MIG-8 document rail update: document settings now prefer Supabase `app_settings`; generated document metadata inserts and sent-status updates prefer Supabase `order_documents`, with Sheets fallback when unavailable.
- GS-MIG-8 quote rail update: quote generation now reads order lines from Supabase order detail first, with `ORDER_LINES` fallback when unavailable.
- GS-MIG-8 sales transaction lifecycle update: slaughter exit confirmation/reconciliation now prefers Supabase `pigs` with additive exit metadata fields, with Sheets fallback when unavailable.
- GS-MIG-8 breeding mutation update: mating creation, pregnancy status updates, litter-link updates, and mating-related movement logs now prefer Supabase `mating_events` and `pig_location_events`, with Sheets fallback when unavailable.
- GS-MIG-8 direct farm write update: create pig/product/pen, single weight entries, optional movement, medical treatment, and movement entries now prefer Supabase canonical farm tables, with Sheets fallback when unavailable.
- GS-MIG-9 litter lifecycle mutation update: litter birth-count correction, stillborn reclassification, purpose review decisions, litter weaning, pig death/removal, litter piglet death, piglet sex/tag updates, and newborn health actions now prefer Supabase canonical update rails when `DATABASE_URL` is available, with Sheets fallback when unavailable.
- GS-MIG-8/9 additive migrations are applied in Supabase: `202606290002_add_pig_exit_fields` and corrected `202606290003_add_litter_lifecycle_fields`.
- Remaining Google Sheets dependencies are now narrower: legacy setup/import/export scripts, Google Drive/document storage integration, and formula-specific farm/litter attention replacement work.
- GS-MIG-11 is merged as PR #30: irrigation status now defaults to Supabase-first `auto` reads with Google Sheets fallback; irrigation remains read-only with hardware control disabled.
- GS-MIG-12 is merged as PR #31: farm dashboard summary now prefers Supabase `pig_current_state`/`pigs` reads with Google Sheets fallback.
- GS-MIG-13 is merged as PR #32: purpose-review apply validation now prefers Supabase pig lookup with Google Sheets fallback.
- GS-MIG-14 is merged as PR #33: new litter creation now prefers a Supabase-first transaction for the litter plus generated piglet records, with Sheets fallback.
- GS-MIG-15 is merged as PR #34: bulk-weight preflight duplicate checks now prefer Supabase `pig_weight_events` with Sheets fallback.
- GS-MIG-16 is merged as PR #35: shared pig-weight pen lookup helpers now use the existing Supabase-first pen service, with Sheets fallback.
- GS-MIG-17 is merged as PR #36: mating/breeding pen validation helpers now prefer Supabase-first pen reads, with existing fallbacks.
- GS-MIG-18 is merged as PR #37: order status-log writes are Supabase-first with Sheets fallback if the Supabase insert fails.
- GS-MIG-19 is merged as PR #38: order-line sync stays Supabase-first and falls back safely if Supabase read/write helpers fail.
- GS-MIG-FINAL is merged as PR #39: final Google Sheets caller audit plus the remaining litter lifecycle validation read cutover.
- Current GS-MIG-FINAL finding: no remaining app caller is classified as an active route that must still be migrated. Remaining Google Sheets callers are safe fallback only, import/export/admin scripts, legacy/reference wrappers, or tests.
- GS-MIG-FINAL code closeout: litter lifecycle validation paths now read Supabase sheet-shaped pig/litter/product rows first, with Google Sheets fallback retained.
- Builds still require 96%+ ticket confidence and a pressure-test plan before merge.
- Cleanup work and operational builds must use clean worktrees from `origin/main`.

## Current Access Status

- `OWNER_ACCESS_ENABLED` is supported.
- Owner login/session exists.
- Owner logout UX exists.
- Owner reported `OWNER_ACCESS_ENABLED=true` login worked in production before ACCESS-1.1; logout UX has been merged and should remain live-verified after deploys.
- Tokens must not be committed.
- Render env vars must be configured separately.
- `/sales/meat-leads` is owner protected when owner access is enabled.

Required owner access env vars:

- `OWNER_ACCESS_ENABLED`
- `OWNER_ACCESS_ALLOW_LOCAL_DEV`
- `OWNER_READ_TOKEN`
- `OWNER_ADMIN_TOKEN`
- `OWNER_SESSION_SECRET`

## SAM Status

- SAM Meat Sales Command Room is live.
- Full-width layout is live.
- Read-only command-state endpoint is live.
- Frontend has not yet been switched to command-state.
- Phase 3A.6 has not started.
- OP-009 SAM pilot readiness 500 must be fixed or safely degraded before Phase 3A.6.
- Operational blockers are being pressure-tested first.
- Current next implementation should be OP-BUILD-1A after OP-1.2 approval: OP-010 logout redirect plus OP-009 pilot readiness degraded handling.

SAM safety remains unchanged:

- no one-click send chain
- no automatic payment/deposit action
- no automatic reservation
- no public posting
- no price, stock, slaughter, butcher, or delivery promise without approved rails

## Oom Sakkie Status

- Oom Sakkie remains Farm Commander under CHARLIE.
- Warm farm command-center direction remains.
- Oom Sakkie UI must not inherit CHARLIE dark styling.
- Oom Sakkie remains behind its own safety and owner approval rails.

## CHARLIE Status

- CHARLIE is the planned top-level owner operating layer.
- CHARLIE Build Relay v0 has started as the first owner-only Telegram/Codex command layer.
- CHARLIE is not built yet as a production UI.
- First CHARLIE surface must be owner-only and read-only/draft-only.
- Build Relay v0 is disabled by default and cannot commit, merge, deploy, run shell commands, write production data, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records.
- CHARLIE Build Relay live Telegram test passed after Render env setup: `/help`, `/next`, `/mission`, and CODEX_CHAT write-gated intake worked.
- Active branch: `charlie-relay-mission-queue`.
- Current CHARLIE build: durable Supabase mission queue plus local owner notification helper.
- CHARLIE mission queue migration is applied: `supabase/migrations/202606300001_create_charlie_mission_queue.sql`.
- New durable queue endpoints/commands are non-executing: `/missions` and `GET /api/charlie/build-relay/missions` list stored mission intake only.
- CHARLIE mission protocol is being formalized so Telegram intake and `planning/CODEX_CHAT.md` follow the same rules.
- Active branch: `charlie-mission-command-console`.
- Current command-console scope: `/mission <id>`, `/debrief <id>`, `/approve <id>`, `/pause <id>`, and `/reject <id>` record or display mission state only. They do not execute build actions.
- Codex pickup bridge is being added through `scripts/charlie_mission_pickup.py` so a running Codex/Cursor session can pull the next approved Telegram mission into `planning/CODEX_CHAT.md` and mark it `in_progress`.
- CHARLIE V1 mission cockpit is active in build: owner-only `/charlie` page, mission queue status cards, decision buttons, and local runner watch mode.
- CHARLIE cockpit and runner remain non-executing: they record/pick up missions only and cannot merge, deploy, apply migrations, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records.

## FRED Status

- FRED is the planned future Transport Commander.
- FRED is not built yet.
- No dispatch, quote, payment, or customer-send automation is approved.

## Ledger Status

- Agent Collaboration Ledger design exists as a planning direction.
- SQL is not implemented in production by this cleanup.
- No ledger migration is approved yet.

## Known Risks

- Original `sam-meat-command-room-release` worktree is dirty and polluted.
- Old screenshots and `external_sources` need later owner review before archive/delete.
- Mutation route guards still need ACCESS-2 later.
- Frontend command-state consumption has not been implemented yet.
- OP-001, OP-002, OP-003, OP-007, OP-008, OP-009, and OP-010 are now at or above the 96% planning confidence gate; OP-004, OP-005, and OP-006 still need inspection.
- Bulk-weight entry had confirmed P0 failures in live owner testing: first browser draft loss after upload failure, then HTML/non-JSON upload failure after draft recovery.
- Google Sheets/Render synchronous upload is now treated as structurally unreliable for large batches. The active P0 is a Supabase-first durable batch rail with chunked processing and row-level retry.

## Last Updated

2026-06-29

