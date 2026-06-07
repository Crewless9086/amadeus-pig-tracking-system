# Claude Review Handoff

## How Charl Should Use This

In Claude Code, say exactly:

```text
Read docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md and run the current review.
```

Claude should not need any extra pasted prompt. The current review scope, files, questions, commands, and output format are all listed below.

## Instructions For Claude

You are working in the **Amadeus Pig Tracking & Sales** repo.

If the user asks you to read this file and review, do this:

1. Read `CLAUDE.md` first.
2. Read the **Current Review Packet** below.
3. Inspect the files listed in **Files/folders to inspect**.
4. Run or recommend the verification commands listed in **Known verification from Codex** as appropriate for your environment.
5. Answer every item in **Design checks**.
6. Use the exact **Deliverable format**.
7. Treat the **Archive / reusable templates** section as background only. Do not review old archived examples unless the user explicitly asks.

## Current Review Packet - Oom Sakkie Local Kiosk And Specialist Roster

## Authority and scope

- **Build order:** `docs/00-start-here/NEXT_STEPS.md`
- **Explicit scope:** Phase 10.6 Oom Sakkie local kiosk/backend-as-brain work through `10.6Z`, plus Phase 10.7A-H specialist manifest, advisory trace-review, access caveat hardening, kiosk review-advisor panel, advisor wording/proxy-test tightening, advisor trace-read consolidation, advisor SQL/test hardening, and kiosk advisor-window/voice-loop counter polish.

Out of scope unless explicitly asked:

- Telegram cutover
- write tools
- physical controls
- backend STT/TTS vendors
- always-on mic
- wake word
- live LLM delegation to specialists
- Agent Factory
- public posting/customer messaging

## Goal

Review the current Oom Sakkie local-only read path and planning scaffolding before daily kiosk use continues:

- Local `/oom-sakkie` kiosk
- Backend-owned `/api/oom-sakkie/message`
- Typed read-only tool registry
- Trace/review/feedback flow
- Browser-only speech controls
- Safety policy and review packet
- Loopback-only review endpoint guard
- DB append-only trace guards
- Planned-only specialist manifest roster
- Advisory-only trace review advisor
- Message/review access policy split and reverse-proxy caveat
- User-action-triggered kiosk Review Advisor panel
- Combined advisor trace reader
- Advisor trace time-window and SQL/test hardening
- Visible Review Advisor time window and Continue Conversation turn counter

## Files/folders to inspect

- `modules/oom_sakkie/`
- `templates/oom-sakkie.html`
- `static/js/oomSakkie.js`
- `static/css/main.css`
- `tests/test_oom_sakkie_service.py`
- `tests/test_oom_sakkie_routes.py`
- `tests/test_frontend_route_contracts.py`
- `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`
- `supabase/migrations/202606060001_create_oom_sakkie_traces.sql`
- `supabase/migrations/202606060002_create_oom_sakkie_trace_feedback.sql`
- `supabase/migrations/202606060003_add_oom_sakkie_safety_notes.sql`
- `supabase/migrations/202606060004_lock_oom_sakkie_trace_append_only.sql`
- `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md`
- `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`
- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`

## What changed

Summary:

- Flask/backend is confirmed as the long-term Oom Sakkie brain.
- n8n/GateKeeper remains Telegram I/O and scheduled workflow; Telegram is not cut over.
- Added local `/oom-sakkie` kiosk and `/api/oom-sakkie/message`.
- Added read-only Oom Sakkie tool registry and deterministic routing.
- Added trace storage, feedback, review summary, filters, search, detail expanders, and review packet.
- Added browser-only speech draft/TTS/continue-conversation controls with stop/cap guards.
- Added quick checks and expanded read-only telemetry/status tools.
- Added safety notes split from stale warnings.
- Added runtime policy, tool catalog, local-access review guard, append-only DB triggers.
- Added planned-only specialist manifests and `/api/oom-sakkie/specialists`.
- Added advisory-only `/api/oom-sakkie/review-advisor`; it prepares a queue and suggestions but does not mark feedback or run autonomously.
- Added explicit `message_endpoint_access` policy and reverse-proxy caveat for review endpoint IP checks.
- Added a user-action-triggered kiosk Review Advisor panel that renders the advisor queue/suggestions without timer polling or marking anything.
- Updated advisor wording from `manual refresh only` to `user-action-triggered, no auto-polling`, matching the implementation.
- Added the inverse forwarded-header test: public `REMOTE_ADDR` plus loopback `X-Forwarded-For` still denies review access.
- Added `list_review_advisor_traces()` so the advisor reads issue traces and unreviewed traces in one combined ranked trace query instead of two separate trace-list reads.
- Added `days` windowing to `list_review_advisor_traces()` so advisor trace reads default to the same 14-day window as the review summary.
- Added `_trace_row` positional mapping coverage and replaced the advisor SQL compiled-constant test with a mocked `psycopg.connect` SQL-capture test.
- Added a visible `last 14 days` label to the kiosk Review Advisor guard line.
- Added a `Voice loop 0 of 5` counter that appears only when Continue Conversation is enabled and updates during continued spoken turns.

Known verification from Codex:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes`
- `node --check static/js/oomSakkie.js`
- `python -m unittest tests.test_frontend_route_contracts`
- Full local unittest suite: `388 tests OK`
- Applied Supabase migrations through `202606060004_lock_oom_sakkie_trace_append_only.sql`.
- Route smokes confirmed:
  - `/api/oom-sakkie/message` stores traces.
  - `/api/oom-sakkie/tools`, `/policy`, `/review-packet`, `/specialists`, `/review-advisor` work locally.
  - review/admin endpoints deny non-local requests with `403 review_access_denied`.
  - `/api/oom-sakkie/message` is not blocked by the review endpoint guard.
  - `send weather to John` answers the read-only weather check and returns a safety note.
  - `start irrigation` remains read-only and does not issue control.
  - `/api/oom-sakkie/review-advisor` returns `mode = advisory_only`, `writes_feedback = false`, and denies non-local requests.

## Design checks

Please inspect specifically:

1. **Split-brain:** Does the implementation preserve backend-as-brain without changing Telegram/n8n routing?
2. **Read-only tools:** Are all current Oom Sakkie tools truly read-only?
3. **Action safety:** Do unsupported write/control/message requests fail closed or produce safety notes?
4. **Irrigation safety:** Does control wording such as `start irrigation` stay read-only and never invoke physical control?
5. **Voice safety:** Is browser voice still opt-in, browser-local, half-duplex enough, and not always-on?
6. **Review endpoint protection:** Is the loopback/private-LAN guard appropriate for `/tools`, `/policy`, `/review-packet`, `/review-advisor`, `/traces`, feedback, and `/specialists`?
7. **Trace audit:** Are trace and feedback tables sufficiently append-only after the DB triggers?
8. **Safety/stale split:** Are `stale_warnings` and `safety_notes` separated cleanly through tools, API response, trace storage, and UI?
9. **Specialist roster:** Is Phase 10.7A safely planned-only, with no live delegation, autonomous loops, or second user-facing brain?
10. **Review advisor:** Is Phase 10.7B advisory-only, with no automatic feedback marking, no hidden write path, no model call, and no autonomous loop?
11. **Access policy:** Does Phase 10.7C document the message endpoint and reverse-proxy assumptions clearly enough, and are the tests honest about current `remote_addr` behavior?
12. **Kiosk advisor panel:** Is Phase 10.7D/E useful and still safe: user-action-triggered only, no timed/background polling, no auto-marking, no HTML injection from trace text, no hidden writes?
13. **Advisor trace reader:** Does Phase 10.7F/G preserve the advisor response shape while reducing duplicate trace-list reads, adding the days window, and avoiding SQL footguns?
14. **Trace row mapping:** Is the positional `_trace_row` mapping sufficiently guarded by tests?
15. **Kiosk honesty polish:** Does Phase 10.7H accurately surface the Review Advisor's 14-day window and the 5-turn continue-conversation cap without changing behavior?
16. **Tests:** What missing tests or browser checks should happen before this is considered daily-use ready?

## Deliverable format

- **Verdict:** pass / pass-with-nits / block.
- **Findings first:** severity ordered, with file/line references where possible.
- **Open questions:** only if a decision is required before continuing.
- **Recommended next slice:** keep it safe and local; do not recommend Telegram cutover, writes, physical controls, always-on mic, wake word, or live specialist delegation unless you explicitly justify why the current daily-use trial is insufficient.

---

## Archive / Reusable Templates

The sections below are older reusable prompt templates and examples for other review types.

For the current Oom Sakkie review, Claude should use only the **Current Review Packet** above unless Charl explicitly asks for another review scope.

## Before you paste anything

1. Open **`docs/00-start-here/NEXT_STEPS.md`** and note the **single phase / subsection** that is in scope (e.g. **Phase 4.1**). Everything outside that is **out of scope** for this review unless you explicitly widen it.
2. Ensure **`CLAUDE.md`** in the repo root is up to date (Claude Code reads it first).

---

## Prompt template — replace `{{PLACEHOLDERS}}`

Paste into Claude Code:

```markdown
You are working in the **Amadeus Pig Tracking & Sales** repo. Read **CLAUDE.md** first, then the files I name below.

## Authority and scope

- **Build order**: `docs/00-start-here/NEXT_STEPS.md` — my **explicit scope for this task** is: **{{1.8 Approval Auto-Reservation}}** only.
- Do **not** propose new phases or widen scope unless I ask — if you find unrelated issues, list them briefly under "**Out of scope**" with one-line rationale each.

## What Cursor / I changed or plan to change

**Summary**: {{SHORT_DESCRIPTION_OF_THE_WORK}}

**Branches / commits / PR**: {{GIT_REF_OR_NONE}}

## Files changed (paths)

{{LIST_FILES_OR_DIFF_SUMMARY}}

## Design checks (answer each)

Work through these **in order**:

1. **Architecture**: Does the change respect `docs/01-architecture/SYSTEM_ARCHITECTURE.md` and boundaries in `CLAUDE.md` (Chatwoot → n8n → Steward/agent → Flask → Sheets)?
2. **DATA_FLOW / ownership**: Does every mutated field trace to `docs/04-n8n/DATA_FLOW.md` and `BUSINESS_RULES` / `SHEET_SCHEMA` as appropriate — no duplicated sources of truth?
3. **n8n workflows**: Is `WORKFLOW_RULES.md` respected? Confirm **formula-driven sheets** stay read-only; confirm **routing** vs **truth** — customer-facing wording must align with **backend / `get_order_context`** for availability and drafts, not only LLM narration.
4. **Order logic**: Does `ORDER_LOGIC.md` still hold for draft/create/sync/reserve/reserve-cancel paths touched?
5. **Regression**: Against `NEXT_STEPS.md` subsection **{{PHASE_AND_SUBSECTION}}**, what is **still missing** for "**Required outcome**" to pass?

## Deliverable format

- **Verdict**: pass / pass-with-nits / block — one sentence each for **risk** and **next concrete step**.
- **Findings**: bullet list grouped by severity (blocking / nit / suggestion).
- **Out of scope** (optional): rabbits we are **not** chasing in this pass.

Extra context dump (payloads / logs):

{{PASTE_LOGS_OPTIONAL}}

```

---

## When to run this (not every change)

Use the handoff for **big or cross-cutting** work. Skip it for tiny, local edits unless you want assurance. Triggers and philosophy: **`docs/00-start-here/HOW_WE_WORK.md` §3**.

Typical triggers:

- Large **`workflow.json`** edits (e.g. `1.0 - Sam-sales-agent-chatwoot`, `1.2 - order-steward`).
- Anything that mixes **routing**, **prompt text**, **Steward payloads**, and **backend** in one change set.
- When you suspect **truth vs narration** mismatch (availability, drafts, reservations).

**When not to bother:** one-file bugfix, typo, comment-only, isolated tiny Code node — unless you are unsure.

## Cursor’s conductor rule

Cursor should **remind you** when a session crosses the “big enough for Claude review” bar; you still **choose** whether to paste into Claude Code. Always scope: "**`NEXT_STEPS.md` §X.Y only.**"

---

## Filled handoff — Phase 1.8: Approval Auto-Reservation (paste everything in the block below)

*Built from `NEXT_STEPS.md` §1.8, `CLAUDE.md`, `ORDER_LOGIC.md`, and current `modules/orders/order_service.py`. Update the “Optional / after implementation” lines with your branch and diff before sending to Claude Code.*

```markdown
You are working in the **Amadeus Pig Tracking & Sales** repo. Read **`CLAUDE.md`** first, then the files listed under **Read first**.

## Authority and scope

- **Build order:** `docs/00-start-here/NEXT_STEPS.md`
- **Explicit scope:** **Phase 1 — §1.8 Approval Auto-Reservation** only.

**Out of scope for this review** (unless I explicitly ask): **§1.9** outbound approval/rejection notifications; **Phase 2+** quotes/invoices; **Phase 4** split-line sync; Sam **`1.0`** prompt copy — unless my diff touches them.

If you find unrelated bugs, list them under **Out of scope** with one line each.

## Goal (from NEXT_STEPS — Required outcome)

Deliver **reserve-on-approve**:

1. **`approve_order`** must set approval state **first** (order becomes **Approved** / approval flags updated as today).
2. **Then** call into the existing **reserve** path for **active** `ORDER_LINES` (reuse **`reserve_order_lines`** semantics from Phase 1.6 — cancelled/collected skipped, no `Pig_ID` skipped, idempotent reserve).
3. If **reservation fails entirely** or **only partially** succeeds:
   - **Do not roll back** the approval in the database/sheets.
   - Surface a **`reserve_warning`** (and/or equivalent structured warning) in the API response for the **web app** to show manual follow-up.
   - Write an appropriate entry to **`ORDER_STATUS_LOG`** documenting the partial/total reserve failure after approval.
4. Per-line outcomes must remain **clear** in the API (align with existing **`reserve_order_lines`** `line_results` / `warning` patterns where possible).

## Current baseline (for you to verify in code)

- **`approve_order`** in `modules/orders/order_service.py` currently: validates **`Pending_Approval`**, updates **`ORDER_MASTER`** to Approved, writes **`ORDER_STATUS_LOG`**, returns `{ success, message, order_id }` — **it does not invoke reservation today**.
- **`reserve_order_lines(order_id)`** in the same module: batch reserve eligible lines; returns **`success`**, **`line_results`**, **`changed_count`**, **`warning`**, **`reserved_pig_count`** — hardened under **Phase 1.6**.
- **HTTP:** `POST /api/orders/<order_id>/approve` in `modules/orders/order_routes.py` returns whatever `approve_order` returns.

Your review should check that the **implementation plan or diff** chains these correctly without breaking lifecycle rules in `docs/02-backend/ORDER_LOGIC.md` and sheet rules in `docs/03-google-sheets/BUSINESS_RULES.md` / `SHEET_SCHEMA.md`.

## What changed / what to review (fill in by human, or paste `git diff --stat`)

**Summary:** _Describe planned or implemented §1.8 work (e.g. “After `approve_order` header update, call `reserve_order_lines`, merge warnings into response, log partial failure”)._

**Branches / commits / PR:** _e.g. branch name, commit SHAs, or “planning only — no commits yet”._

**Files changed (paths):**

_read from `git diff --stat` or list manually, e.g._

- `modules/orders/order_service.py`
- `modules/orders/order_routes.py`
- _Web app order detail component if API contract changes_
- `docs/02-backend/ORDER_LOGIC.md` (if behavior documented)

## Read first

1. `docs/00-start-here/NEXT_STEPS.md` — **§1.8** only
2. `docs/02-backend/ORDER_LOGIC.md` — approval, reserve, release
3. `docs/04-n8n/DATA_FLOW.md` — only if the diff changes Steward or order API contracts
4. `modules/orders/order_service.py` — `approve_order`, `reserve_order_lines`
5. `modules/orders/order_routes.py` — `/approve`

## Design checks (answer each)

1. **Architecture:** Does the change respect Chatwoot → n8n → Steward/agent → Flask → Sheets and keep **formula-driven sheets** read-only?
2. **Approval vs inventory:** Is **approval** still a single, atomic header transition, with **reservation** as a **second phase** that can fail without undoing approval?
3. **Observability:** Will ops see **log + API** evidence when pigs did not all reserve (per **`ORDER_STATUS_LOG`** and response body)?
4. **UI contract:** Does the **web app** receive enough structured fields (`reserve_warning`, `line_results`, counts) to match **Phase 1.6**–style messaging?
5. **Regression:** Against **§1.8 Required outcome**, list anything **still missing**.

## Deliverable format

- **Verdict:** pass / pass-with-nits / block — one sentence **risk** + one **next concrete step**.
- **Findings:** bullets by severity (blocking / nit / suggestion).
- **Out of scope:** optional.

**Optional — paste API response sample or execution log after a test approve:**

_(paste here)_

```
```

### How to use

1. Copy everything from the line **`You are working in the Amadeus…`** down to **`(paste here)_`** (inclusive), i.e. the full prompt inside the fenced block above — **do not** copy the wrapper sections titled “Filled handoff” / “How to use”.
2. Fill in **Summary**, **git ref**, and **files changed** (or write *planning only — no commits yet*).
3. Paste into **Claude Code** with this repo open.
