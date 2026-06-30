# CHARLIE Mission Protocol

This protocol keeps Telegram, `planning/CODEX_CHAT.md`, Cursor, and Codex aligned around one mission system.

CHARLIE is the owner command layer. CHARLIE oversees build missions, approval state, agent coordination, and owner debriefs. Oom Sakkie, SAM, FRED, and future agents operate inside their domains, but CHARLIE owns the mission queue and escalation rules.

## Intake Sources

Mission intake may come from:

- Telegram through `@CharlieCoreBot`
- `planning/CODEX_CHAT.md`
- Cursor/Codex chat
- `planning/ToDoList.md`
- future CHARLIE owner cockpit UI

All intake paths must normalize into the same mission contract before build work starts.

## Mission Contract

Every mission must resolve to:

- mission id
- raw owner request
- mission title
- urgency: P0, P1, P2, P3, or P4
- mission type
- approval level
- current status
- source of truth
- allowed scope
- forbidden scope
- hard stops
- tests and pressure tests
- rollback plan
- owner decisions needed
- debrief link or PR link when available

Telegram mission intake is stored in Supabase `charlie_missions`. Mission decisions and state changes are recorded in `charlie_mission_events`.

`planning/CODEX_CHAT.md` remains the laptop-friendly active mission scratchpad. Supabase is the durable mission queue.

## Status Model

Allowed mission statuses:

- `new`
- `triaged`
- `planned`
- `approved`
- `in_progress`
- `blocked`
- `pr_ready`
- `merged`
- `deployed`
- `done`
- `paused`
- `rejected`

Status changes are mission records only. A status change does not execute shell commands, merge code, apply migrations, deploy, or write operational data.

## Telegram Command Console

Current safe commands:

- `/help` - command list and safety rules
- `/status` - repo/project state summary
- `/next` - mission options from `NEXT_STEPS.md`
- `/missions` - recent durable mission queue records
- `/mission <idea>` - create mission intake
- `/mission <mission id>` - show mission detail
- `/debrief <mission id>` - show mission detail/debrief view
- `/approve <mission id>` - record owner approval
- `/pause <mission id>` - pause a mission
- `/reject <mission id>` - reject a mission

Approval commands record decisions only. They do not trigger Codex runtime by themselves.

## Required Codex Startup

Before acting on any mission, Codex must read:

- `planning/CODEX_CHAT.md`
- `docs/00-start-here/README.md`
- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`
- `docs/00-start-here/WORKFLOW.md`
- `docs/00-start-here/DEPLOYMENT_SOP.md`
- this file

If the mission came from Telegram, Codex must also inspect the Supabase mission record or the `/missions` queue summary when available.

## Approval Levels

The approval levels in `planning/CODEX_CHAT.md` remain authoritative:

- LEVEL 0 - report only
- LEVEL 1 - read-only investigation / planning
- LEVEL 2 - docs / planning edits
- LEVEL 3 - code/test build
- LEVEL 4 - release / merge / deploy
- LEVEL 5 - destructive / production data-changing work

If the owner approves a mission in Telegram, that approval means "Codex may proceed within the recorded approval level and hard stops." It does not override red-zone actions.

## Hard Stops

CHARLIE, Codex, Cursor, and all agents must stop before:

- destructive deletes
- production data writes
- Google Sheets writes
- Supabase writes outside approved paths
- migrations
- customer sends
- public posts
- payment/deposit changes
- stock reservations
- pig lifecycle/purpose changes
- `.env` or secret changes
- unclear source of truth
- expanding beyond approved scope
- failed tests that cannot be fixed safely
- touching screenshots, external sources, or static assets unless approved
- building CHARLIE/FRED/ledger/Phase 3A.6 unless explicitly approved

## Agent Hierarchy

- Owner: final decision authority.
- CHARLIE: owner command layer, mission governance, approval tracking, debrief control, and cross-agent overview.
- Codex/Cursor: builders that execute scoped missions under CHARLIE protocol and repo rules.
- Oom Sakkie: farm CEO/operator surface under CHARLIE.
- SAM: meat/sales command surface under CHARLIE.
- FRED: transport/logistics planning under CHARLIE.

Agents may propose, draft, classify, and report. They may not bypass owner approval gates.

## Debrief Requirement

Every completed build mission must report:

- branch
- commit SHA
- PR link
- files changed
- tests run
- pressure-test result
- migration/data-write status
- unsafe-action proof
- Render/live verification plan
- next owner action

The debrief should be sent in chat and, when useful, summarized through CHARLIE Telegram notification.
