# Current State

This is the short live-state dashboard for the project. Keep it current after accepted phases, PR merges, and deploys.

## Beacon Marketing Department Evidence - 2026-07-12

- Beacon is the Marketing Department Leader, with Strategy, Creative, Media Librarian, Scheduler, and Performance specialist modules under her.
- `/charlie-agents` reads live Beacon media, Facebook execution, manual-post, and campaign-performance evidence and excludes smoke-test rows from production metrics.
- Current production evidence is one approved asset and one owner-confirmed Facebook campaign post, with no production performance rows or qualified-lead attribution yet. The current Workforce evidence score is 33%, labelled `owner_approved_posting`.
- `/sales/beacon-media` remains the operating workspace for media review, campaign packets, exact owner-confirmed Facebook posting, manual performance evidence, and boost recommendations.
- ElevenLabs and Happy Horse 1.0 are planned creative-provider candidates only. No provider call, spend, scheduling, or public-use authority is enabled.
- Six owner-gated Beacon growth missions are stored in CHARLIE CORE for governance/targets, opportunity scanning, creative providers, campaign scheduling, attribution/finance, and optimization.

## Production State

`origin/main` currently includes:

- `bbab465` Fix Supabase litter status outcomes (#50)
- `b89d858` Show CHARLIE runner handoff status (#49)
- `9ddd2f6` Add CHARLIE approval level handoff (#48)
- `16e851f` Fix Supabase litter stillborn reconciliation (#47)
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

## Mission Loop Foundation

- Branch `mission-loop-foundation` adds the local CHARLIE Mission Loop foundation: mission contract, Windows verify gate, trust ledger skeleton, budget guard placeholder, safe Build Relay notification stub, and manual NEXT_STEPS-to-CODEX_CHAT fallback helper.
- This foundation makes no Claude/Fable/GLM/OpenRouter/GPT-5.6 calls, sends no live Telegram messages unless explicitly enabled/configured, and performs no production data writes.
- `scripts/verify_mission.ps1` is the local final gate for this layer and refuses forbidden staged files such as `.env`, `.claude/`, `external_sources/`, `screenshots/`, `static/assets/`, `test-results/`, and `planning/Prompts.md`.
- Trust starts in `watch` tier in `loop/memory/trust.tsv`; later layers must earn `queue` or `auto` via logged deterministic passes.
- MISSION-LOOP-5/6 add the owner Telegram `/next` button flow and local live relay. `/next` reads live Supabase `charlie_missions` first and falls back to `NEXT_STEPS.md` only when Supabase is unavailable or empty; the current CODEX_CHAT write is a manual transitional handoff, not primary mission state.
- MISSION-LOOP-6 adds the deterministic model budget gate skeleton. GPT-5.6 Sol/Terra/Luna routing is planned but disabled; no model APIs are called by the relay or mission loop.
- MISSION-LOOP-6.5 alignment sets the architecture rule: Supabase CHARLIE CORE is authoritative, Telegram controls CORE, `CODEX_CHAT.md` is manual/debug fallback only, and Loop 7A must use Supabase `mission_id` action cards instead of file-first handoffs.
- MISSION-LOOP-7 adds Supabase `mission_id` action cards, state revalidation, owner-safe mission decisions, blocked/review return actions, and runner/queue visibility. Live mission selection no longer writes CODEX_CHAT.
- MISSION-LOOP-8A/B adds an opt-in Windows Scheduled Task installer for the local relay plus richer `/status`, `/queue`, and `/blocked` health reporting.
- MISSION-LOOP-8C/D connects trust and budget policy to a deterministic GPT-5.6 routing recommendation. Live model calls remain disabled; Loop 8E is not implemented.

## SAM Live Stock Completion Program

- `docs/06-operations/SAM_LIVE_STOCK_COMPLETION_PROGRAM.md` is the accepted completion contract and production graduation standard.
- SAM now normalizes language, message intent, emoji-only acknowledgements, voice-note transcripts, and image classifications before planning. Image-derived facts remain untrusted and media is not stored.
- The next-action planner gives durable order/quote state precedence over message wording, then handles location, pictures, delivery, collection, breeding, price, order changes, and natural closes.
- LLM and deterministic replies are action-conditioned and language-aware; correction retrieval ranks by message similarity, language, stage, and reply class.
- The owner can prepare a quote, loading sheet, removal certificate, and health declaration as one idempotent sales-pack action. This sends nothing and reserves nothing.
- The owner-only learning scorecard and replay runner enforce production evidence thresholds. Autoreply remains off and no reply class can self-enable.
- Live baseline at implementation time: 50 captured owner replies across 17 conversations. Historical rows do not yet contain the new reply-class metadata and do not justify autonomy graduation.

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
- Litter operations fallback fix is active in build: `/litters` derives useful statuses from lifecycle counts when sheet `Litter_Status` is blank/Unknown, and litter detail lifecycle outcomes classify `Died` as dead instead of other.
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
- CHARLIE Build Relay and owner-only `/charlie` Mission Control are live as the first Telegram/dashboard mission layer.
- First CHARLIE surface remains owner-only and record/handoff focused.
- Build Relay v0 is disabled by default and cannot commit, merge, deploy, run shell commands, write production data, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records.
- CHARLIE Build Relay live Telegram test passed after Render env setup: `/help`, `/next`, `/mission`, and CODEX_CHAT write-gated intake worked.
- Current CHARLIE foundation: durable Supabase mission queue plus local owner notification helper.
- CHARLIE mission queue migration is applied: `supabase/migrations/202606300001_create_charlie_mission_queue.sql`.
- New durable queue endpoints/commands are non-executing: `/missions` and `GET /api/charlie/build-relay/missions` list stored mission intake only.
- CHARLIE mission protocol is being formalized so Telegram intake and `planning/CODEX_CHAT.md` follow the same rules.
- Current command-console scope: `/mission <id>`, `/debrief <id>`, `/approve <id>`, `/pause <id>`, and `/reject <id>` record or display mission state only. They do not execute build actions.
- Codex pickup bridge is being added through `scripts/charlie_mission_pickup.py` so a running Codex/Cursor session can pull the next approved Telegram mission into `planning/CODEX_CHAT.md` and mark it `in_progress`.
- CHARLIE V1 mission cockpit is active in build: owner-only `/charlie` page, mission queue status cards, decision buttons, and local runner watch mode.
- CHARLIE cockpit and runner remain non-executing: they record/pick up missions only and cannot merge, deploy, apply migrations, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records.
- CHARLIE runner approval-level handoff is active in build: Telegram and `/charlie` can record LEVEL 1, LEVEL 3, and LEVEL 4 mission authority; the Codex pickup bridge writes runner mode into `planning/CODEX_CHAT.md`.
- Current rule: Telegram/dashboard do not execute shell commands directly. A running Codex/Cursor session executes within the recorded approval level and hard stops.
- CHARLIE runner visibility is active in build: `/charlie` will show active mission, next approved mission waiting for pickup, and the local continuous runner command.
- Continuous runner command: `.\venv\Scripts\python.exe scripts\charlie_mission_pickup.py --watch --continuous --notify --execute-codex --watch-release --auto-merge-pr --interval-seconds 30`.
- CHARLIE Telegram/dashboard alignment is active in build: `/next` should now show the same live mission handoff state as `/charlie` before falling back to static `NEXT_STEPS.md` mission options.
- CHARLIE Mission Vault V1 is active in build: dashboard intake, Supabase mission metadata vault, media/reference links, and planner/architect/builder/tester/reviewer role tracking.
- CHARLIE Stage 6 is active in build: shared mission context pack, owner-visible planner/architect/builder/tester/reviewer handoff controls, `/review`, `/workflow`, and `/done` commands.
- CHARLIE Stage 7 is active in build: local runner heartbeat/status, start/status/stop helper script, dashboard runner active/stale/not-started display, and Telegram `/status` runner visibility.
- CHARLIE Stage 7 safety fix is active in build: Windows runner PID liveness checks use a non-destructive process-handle probe instead of `os.kill(pid, 0)`, and the dashboard runner-status route performs one local runner status check per request.
- CHARLIE Stage 8 owner review gate is active in build: local execution stops at `pr_ready`, `/charlie` has an Owner Review section with findings/errors/bugs/test evidence/local preview fields, and owner decisions can final-approve, send back with comments, pause, reject, or mark done.
- CHARLIE mission intake media is active in build: `/charlie` can capture bounded pasted/dropped screenshot images into existing mission metadata media references, alongside URL/path/note references. Dedicated media tables, Google Drive/object storage, and deletion automation remain unapproved later storage work.
- Stage 8 final approval records LEVEL 4 release permission as `release_approved`; it must not return to normal `approved` build pickup. Send-back records comments in the Mission Vault and returns the mission to `approved` for another local runner/Codex pass.
- CHARLIE full local automation runner is active in build: after approval, the local runner can pick up the mission, run `codex exec`, populate the owner review packet, move the mission to `pr_ready`, and send the owner a Telegram review notification.
- CHARLIE local release bridge is active in build: after final owner approval records `release_approved`, the local runner can merge a reviewed PR reference with `--auto-merge-pr`, or block and notify if release evidence is missing. No-release missions can still be explicitly closed with `scripts/charlie_release_bridge.py --complete-no-release`.
- Render cannot see the laptop `.charlie_runner` heartbeat. The live `/charlie` dashboard must label local runner state as unavailable on Render instead of implying the laptop runner is stopped.
- Current truth: approving a mission records permission. Automatic pickup requires the local runner to be active.
- CHARLIE still does not run builds from Telegram/dashboard directly. Codex/Cursor remains the execution boundary until later parallel-agent controls exist.
- CHARLIE Stage 1 completion-spine fix (branch `charlie-stage1-completion-spine`) is in build: it addresses the overnight failure where the same simple mission never landed after 8+ hours. Root causes fixed: (1) **cross-session evidence loss** — a resumed downstream agent (e.g. QA/Red-Team) was handed an empty `previous_agent_artifacts` and re-blocked already-passed work; upstream artifacts are now recovered from durable mission memory. (2) **session-local loop cap** — the backflow retry counter reset every runner session, so a repeated blocker looped overnight; the hard-loop cap is now mission-durable and converts a repeated blocker into an honest owner block. Both changes are additive and behind no behavioral flag; the full CHARLIE test suite (346 tests) stays green. Still pending in later Stage 1 increments: objective/realistic gate for simple low-risk missions (the 96% adversarial confidence floor), explicit done-lock sealing of passed stages, the reliability spine (atomic claim/lease, dead-runner recovery, stuck watchdog), and pipeline right-sizing + per-stage model routing for token cost.

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

2026-06-30

