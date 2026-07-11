# CODEX_CHAT Mission Selection Workflow

Last updated: 2026-07-11

This workflow turns `docs/00-start-here/NEXT_STEPS.md` into a local active mission file without adding Telegram buttons yet.

## Canonical Files

- Mission menu: `docs/00-start-here/NEXT_STEPS.md`
- Active laptop mission file: `planning/CODEX_CHAT.md`
- Current truth: `docs/00-start-here/CURRENT_STATE.md`
- Contract: `docs/06-operations/MISSION_LOOP_CONTRACT.md`

## Local Helper

`scripts/codex_next_steps.py` can:

- read `NEXT_STEPS.md`;
- extract the top P0/P1/P2 options;
- print options 1-5;
- write the selected mission into `planning/CODEX_CHAT.md`;
- archive existing CODEX_CHAT content before writing.

Examples:

```powershell
python scripts/codex_next_steps.py
python scripts/codex_next_steps.py --select 1 --owner-intent "Run this as a LEVEL 3 scoped build mission"
```

Tests use temporary files and do not overwrite the real `planning/CODEX_CHAT.md`.

## CODEX_CHAT Sections

The generated mission file contains:

- ACTIVE MISSION
- OWNER INTENT
- AUTHORITY LEVEL
- ALLOWED FILES
- FORBIDDEN FILES
- DONE WHEN
- TESTS TO RUN
- PRESSURE TESTS
- CURRENT STATUS
- FINAL REPORT

## Safety

- Invalid options are rejected.
- Empty `NEXT_STEPS.md` is rejected.
- Existing CODEX_CHAT content is archived before replacement.
- No Telegram buttons are wired in this layer.
- No model API calls are made.

