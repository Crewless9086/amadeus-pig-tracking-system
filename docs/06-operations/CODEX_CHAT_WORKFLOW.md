# CODEX_CHAT Manual Handoff Workflow

Last updated: 2026-07-11

This workflow is a local/manual fallback for Codex handoff. It is not the primary CHARLIE CORE mission system.

Supabase `charlie_missions` and CHARLIE CORE are authoritative. Telegram `/next` reads Supabase first. `docs/00-start-here/NEXT_STEPS.md` is planning backlog/fallback only, and `planning/CODEX_CHAT.md` is manual/local/debug handoff only.

## Canonical Files

- Primary mission store: Supabase `charlie_missions`
- Primary controller: CHARLIE CORE
- Fallback/planning menu: `docs/00-start-here/NEXT_STEPS.md`
- Manual laptop handoff file: `planning/CODEX_CHAT.md`
- Current truth: `docs/00-start-here/CURRENT_STATE.md`
- Contract: `docs/06-operations/MISSION_LOOP_CONTRACT.md`

## Local Helper

`scripts/codex_next_steps.py` remains available for manual fallback handoff. It can:

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

## Telegram Button Layer

Loop 5 originally wired this local workflow to the owner Telegram command `/next`. Loop 6.5 alignment changes the architecture direction:

- `/next` reads Supabase `charlie_missions` first;
- `NEXT_STEPS.md` is fallback only if Supabase is unavailable or empty;
- current selection still writes a manual CODEX_CHAT handoff as a transitional bridge;
- Loop 7A must replace option-number callbacks with Supabase `mission_id` action cards;
- normal future Telegram control must not write CODEX_CHAT by default;
- no Codex run starts from the button itself.

## Live Relay Layer

Loop 6 adds `scripts/charlie_telegram_relay.py`, a local runner that receives Telegram updates and routes `/start`, `/status`, `/next`, and mission-selection callbacks through the same workflow.

The relay still only prepares a manual handoff file when a selection is made. It does not execute shell commands, run Codex, schedule missions, auto-merge, call model APIs, or write production data.

## Planned `/handoff` Separation

Future Loop 7A mission controls should operate on Supabase `mission_id` state. If CODEX_CHAT remains useful, expose it only as an explicit manual/debug action such as `/handoff <mission_id>`, not as the default `/next` callback behavior.

## GPT-5.6 Note

GPT-5.6 routing is planned but disabled. Sol, Terra, and Luna are future support modules behind the budget gate and trust ledger. Loop 6.5 performs alignment only; no live model calls are allowed.
