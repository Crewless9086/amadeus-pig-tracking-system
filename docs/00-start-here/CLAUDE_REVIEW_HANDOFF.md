# Claude Code review handoff (copy-paste)

Use when you want **Claude Code** to double-check Cursor’s plan or implementation against this repo’s design — especially **n8n + Flask + Sheets** boundaries.

## Before you paste anything

1. Open **`docs/00-start-here/NEXT_STEPS.md`** and note the **single phase / subsection** that is in scope (e.g. **Phase 4.1**). Everything outside that is **out of scope** for this review unless you explicitly widen it.
2. Ensure **`CLAUDE.md`** in the repo root is up to date (Claude Code reads it first).

---

## Prompt template — replace `{{PLACEHOLDERS}}`

Paste into Claude Code:

```markdown
You are working in the **Amadeus Pig Tracking & Sales** repo. Read **CLAUDE.md** first, then the files I name below.

## Authority and scope

- **Build order**: `docs/00-start-here/NEXT_STEPS.md` — my **explicit scope for this task** is: **{{PHASE_AND_SUBSECTION}}** only.
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
