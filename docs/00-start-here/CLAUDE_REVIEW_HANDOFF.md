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

## When to run this

- Large **`workflow.json`** edits (e.g. `1.0 - Sam-sales-agent-chatwoot`, `1.2 - order-steward`).
- Anything that mixes **routing**, **prompt text**, **Steward payloads**, and **backend** in one incident.
- When you suspect **truth vs narration** mismatch (availability, drafts, reservations).

## Cursor’s conductor rule

Tell Cursor explicitly: "**Scope this to `NEXT_STEPS.md` §X.Y only.**" Paste the filled handoff prompt when you spawn Claude Code.
