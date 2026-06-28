# Scratch (`planning/ToDoList.md`)

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
