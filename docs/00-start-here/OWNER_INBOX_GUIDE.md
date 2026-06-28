# Owner Inbox Guide

This guide explains where raw owner notes go before they become canonical docs.

## Current Intake

Use:

```text
planning/ToDoList.md
```

for rough notes, bugs, ideas, screenshots references, and questions.

This file is scratch. It is not production truth.

When a note is triaged, copy the action into `NEXT_STEPS.md` and update `CURRENT_STATE.md` if it changes live status or risk.

## Future Inbox Structure

Proposed folders:

```text
planning/inbox/
  notes/
  screenshots/
  prompts/
  raw-cursor-reports/
  processed/
```

## Rules

The inbox is not production truth.

Cursor/Codex may read inbox material and triage it into:

- `docs/00-start-here/NEXT_STEPS.md`
- `docs/00-start-here/CURRENT_STATE.md`
- specific module docs when a durable decision is made

Screenshots should stay in `planning/inbox/screenshots/` until processed. They should not live in docs unless they are active reference assets.

Decisions must be copied into canonical docs. Do not leave important decisions only in the inbox.

Processed notes can later move to:

```text
planning/inbox/processed/YYYY-MM/
```

Do not delete owner notes, screenshots, prompts, or raw reports without explicit owner approval.

Do not commit secrets, `.env`, tokens, customer private data, screenshots, or external source dumps unless a later owner approval explicitly allows it.
