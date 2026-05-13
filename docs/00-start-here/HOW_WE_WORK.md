# How we work: phases, reviews, and testing

Single roadmap: **`NEXT_STEPS.md`**. This file is **how** we execute it without skipping ahead or reviewing endlessly.

---

## 1. Working position (update when you finish a subsection or change focus)

Edit the lines below so every session starts with clarity.

| Field | Value |
|--------|--------|
| **Today’s focus** | `NEXT_STEPS.md` § **Phase 5.8** — Formal Quote Request Flow |
| **Status** | Phase 5.8 automatic quote-readiness implementation in repo; live import/retest next |
| **Current focus** | `NEXT_STEPS.md` Section **5.8** - Formal quote request flow |
| **Current last verified** | **2026-05-13** - local auto-quote helper check: missing payment blocks generation; quote-ready draft generates once; unchanged draft skips duplicate quote |
| **Last verified** | **2026-05-09** — §1.8 approval auto-reservation live checks |

**Rule:** Do **not** start a later phase because it feels urgent, unless **`NEXT_STEPS.md`** is officially updated to reprioritise. Cursor should default to **the next incomplete required outcome** in order.

---

## 2. Phase-by-phase (no jumping the line)

1. Open **`NEXT_STEPS.md`** and find the **first** subsection that is **not** marked complete for its **required outcome**.
2. Scope all work and testing to that subsection until its checklist passes or it is explicitly **blocked** and logged.
3. New issues discovered along the way get a **one-line note** under the correct phase in **`NEXT_STEPS.md`** (or **`CURRENT_STATE.md`** for symptoms), not a new improvisation lane.

---

## 3. Claude Code review — **not** every time

**You do not** need to paste the handoff prompt on every small fix.

### When Cursor should **proactively tell you** to run **`CLAUDE_REVIEW_HANDOFF.md`**

The Cursor (conductor) agent should **say so explicitly** when a change is **large or cross-cutting**, for example:

- Edits to **`workflow.json`** that change routing, merges, or many nodes (especially **`1.0`** / **`1.2`**).
- Same logical change touching **n8n + Flask + docs** together.
- Ambiguity between **customer-facing text** and **backend / Steward truth** (availability, drafts, reservations).
- Any diff that is hard to review in one glance and could violate **`DATA_FLOW.md`** or **`WORKFLOW_RULES.md`**.

Reminder text can be short, e.g.: *This is cross-cutting — worth a Claude Code pass using `CLAUDE_REVIEW_HANDOFF.md` scoped to §X.Y.*

### When a Claude review is **optional**

- Small, local fixes (one function, one doc typo, one isolated Code node) with a clear single-file diff.
- Pure documentation rewording with no behavior change.

---

## 4. Testing: clear order, flexible wording

**Goal:** Repeatable checks **without** pretending humans only speak one phrase.

### A. Scripted “golden path” (per phase subsection)

When **`NEXT_STEPS`** lists a regression sequence, treat it as **information order**, not exact wording:

- Each **step** is **what must become true** in the conversation or sheets (e.g. quantity → sex split → band → location → timing → payment).
- For each step, **one example message** is enough to keep the run orderly; you may **paraphrase** (synonyms, short vs long, UK/US spelling) **unless** the test is specifically about parsing a fixed phrase.

**Pass/fail** is about **steward + sheets + Sam behavior**, not about matching sample text character-for-character.

### B. Optional human smoke test (random style)

Sometimes we need **real messiness**: typos, out-of-order answers, changing mind, minimal replies.

- Cursor will **call this out** when it matters: e.g. after a scripted pass, or when testing **robustness** of routing/memory rather than one happy path.
- You run **one** conversation in **whatever style you like** (follow Sam, fight Sam, or random). Outcome: we see where the system drifts — **does not replace** the phase’s **required outcome** checklist unless we decide to extend the phase.

---

## 5. Closing a subsection

A subsection is “done enough to move on” when:

1. **`NEXT_STEPS`** **required outcome** bullets for that subsection are satisfied (or explicitly deferred with a dated note in **`NEXT_STEPS`**).
2. **`WORKING_POSITION`** (table in §1 above) is updated.
3. If the work was **cross-cutting**, a **Claude review** was at least **offered** (you may still skip if you accept the risk).

---

## Related files

| File | Use |
|------|-----|
| `docs/00-start-here/NEXT_STEPS.md` | **What** to do, in **what order** |
| `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` | **When** you do ask Claude Code — copy-paste prompt |
| `CLAUDE.md` | Repo root — architecture + conductor/worker + Cursor reminder rule |
| `planning/ToDoList.md` | Scratch only — not a second plan |
